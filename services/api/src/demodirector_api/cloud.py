from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from demodirector_contracts import (
    ProductUnderstanding,
    Project,
    ResearchSource,
    Scene,
    Storyboard,
    Timeline,
    TimelineHistoryState,
    TimelineVersion,
    VideoExport,
    WebsiteInspection,
)
from google.api_core.exceptions import FailedPrecondition
from google.cloud import firestore, tasks_v2

from demodirector_api.exports import StoredExport
from demodirector_api.repositories import TimelineVersionConflict


def _snapshot_data(snapshot: Any) -> dict[str, Any]:
    return snapshot.to_dict() or {}


class FirestoreProjectRepository:
    """Durable project metadata repository used by the Cloud Run API."""

    def __init__(self, client: firestore.Client) -> None:
        self.collection = client.collection("projects")

    def create(self, project: Project) -> Project:
        self.collection.document(project.id).create(project.model_dump(mode="json"))
        return project

    def get(self, project_id: str) -> Project | None:
        snapshot = self.collection.document(project_id).get()
        return None if not snapshot.exists else Project.model_validate(_snapshot_data(snapshot))

    def update(self, project: Project) -> Project | None:
        reference = self.collection.document(project.id)
        if not reference.get().exists:
            return None
        reference.set(project.model_dump(mode="json"))
        return project

    def list(self, owner_user_id: str | None = None) -> list[Project]:
        projects = [
            Project.model_validate(_snapshot_data(snapshot))
            for snapshot in self.collection.stream()
        ]
        if owner_user_id is not None:
            projects = [project for project in projects if project.owner_user_id == owner_user_id]
        return sorted(projects, key=lambda project: (-project.updated_at.timestamp(), project.id))

    def delete(self, project_id: str) -> bool:
        reference = self.collection.document(project_id)
        if not reference.get().exists:
            return False
        reference.delete()
        return True


class FirestoreResearchSourceRepository:
    """Persists normalized website and partner evidence by project."""

    def __init__(self, client: firestore.Client) -> None:
        self.collection = client.collection("project_research_sources")

    def replace_partner_sources(
        self,
        project_id: str,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]:
        return self._replace(project_id, "partner_search", sources)

    def replace_website_sources(
        self,
        project_id: str,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]:
        return self._replace(project_id, "website", sources)

    def _replace(
        self,
        project_id: str,
        source_type: str,
        sources: list[ResearchSource],
    ) -> list[ResearchSource]:
        if any(source.project_id != project_id for source in sources):
            raise ValueError("all research sources must belong to the requested project")
        if any(source.source_type != source_type for source in sources):
            raise ValueError(f"all sources must have source_type={source_type}")
        reference = self.collection.document(project_id)
        snapshot = reference.get()
        existing = [] if not snapshot.exists else _snapshot_data(snapshot).get("sources", [])
        retained = [item for item in existing if item.get("source_type") != source_type]
        reference.set(
            {"sources": [*retained, *(source.model_dump(mode="json") for source in sources)]}
        )
        return sources

    def list_for_project(self, project_id: str) -> list[ResearchSource]:
        snapshot = self.collection.document(project_id).get()
        if not snapshot.exists:
            return []
        sources = [
            ResearchSource.model_validate(item)
            for item in _snapshot_data(snapshot).get("sources", [])
        ]
        return sorted(sources, key=lambda source: (-source.retrieved_at.timestamp(), source.title))


class FirestoreWebsiteInspectionRepository:
    def __init__(self, client: firestore.Client) -> None:
        self.collection = client.collection("website_inspections")

    def save(self, inspection: WebsiteInspection) -> WebsiteInspection:
        self.collection.document(inspection.project_id).set(inspection.model_dump(mode="json"))
        return inspection

    def get(self, project_id: str) -> WebsiteInspection | None:
        snapshot = self.collection.document(project_id).get()
        return (
            None
            if not snapshot.exists
            else WebsiteInspection.model_validate(_snapshot_data(snapshot))
        )


class FirestoreProductUnderstandingRepository:
    def __init__(self, client: firestore.Client) -> None:
        self.collection = client.collection("product_understandings")

    def save(self, understanding: ProductUnderstanding) -> ProductUnderstanding:
        self.collection.document(understanding.project_id).set(
            understanding.model_dump(mode="json")
        )
        return understanding

    def get(self, project_id: str) -> ProductUnderstanding | None:
        snapshot = self.collection.document(project_id).get()
        return (
            None
            if not snapshot.exists
            else ProductUnderstanding.model_validate(_snapshot_data(snapshot))
        )


class FirestoreStoryboardRepository:
    """Keeps immutable storyboard versions in one project-scoped document."""

    def __init__(self, client: firestore.Client) -> None:
        self.collection = client.collection("storyboard_histories")

    def save(self, storyboard: Storyboard) -> Storyboard:
        reference = self.collection.document(storyboard.project_id)
        snapshot = reference.get()
        versions = [] if not snapshot.exists else _snapshot_data(snapshot).get("versions", [])
        next_version = len(versions) + 1
        versioned = storyboard.model_copy(update={"version": next_version})
        reference.set(
            {
                "project_id": storyboard.project_id,
                "versions": [*versions, versioned.model_dump(mode="json")],
            }
        )
        return versioned

    def get_latest(self, project_id: str) -> Storyboard | None:
        snapshot = self.collection.document(project_id).get()
        if not snapshot.exists:
            return None
        versions = _snapshot_data(snapshot).get("versions", [])
        return None if not versions else Storyboard.model_validate(versions[-1])


class FirestoreTimelineRepository:
    """Durable timeline history used by Cloud Run revisions and scale-to-zero restarts."""

    def __init__(self, client: firestore.Client) -> None:
        self.collection = client.collection("timeline_histories")

    @staticmethod
    def _state(payload: dict[str, Any]) -> TimelineHistoryState:
        versions = [TimelineVersion.model_validate(item) for item in payload["versions"]]
        current_version = int(payload["current_version"])
        current = next(item for item in versions if item.version == current_version)
        return TimelineHistoryState(
            current=current,
            can_undo=current_version > 1,
            can_redo=current_version < max(item.version for item in versions),
        )

    def initialize(self, timeline: Timeline) -> TimelineHistoryState:
        reference = self.collection.document(timeline.project_id)
        snapshot = reference.get()
        if snapshot.exists:
            return self._state(_snapshot_data(snapshot))
        version = TimelineVersion(
            project_id=timeline.project_id,
            version=1,
            timeline=timeline,
            change_summary="Initial timeline",
            affected_ids=[],
        )
        payload = {
            "project_id": timeline.project_id,
            "current_version": 1,
            "versions": [version.model_dump(mode="json")],
        }
        reference.create(payload)
        return self._state(payload)

    def current(self, project_id: str) -> TimelineHistoryState | None:
        snapshot = self.collection.document(project_id).get()
        return None if not snapshot.exists else self._state(_snapshot_data(snapshot))

    def commit(
        self,
        expected_version: int,
        timeline: Timeline,
        change_summary: str,
        affected_ids: list[str],
    ) -> TimelineHistoryState:
        reference = self.collection.document(timeline.project_id)
        snapshot = reference.get()
        if not snapshot.exists:
            raise TimelineVersionConflict("Timeline history has not been initialized.")
        payload = _snapshot_data(snapshot)
        current_version = int(payload["current_version"])
        if current_version != expected_version:
            raise TimelineVersionConflict("Timeline history changed before this edit was applied.")
        versions = [
            TimelineVersion.model_validate(item)
            for item in payload["versions"]
            if int(item["version"]) <= current_version
        ]
        next_version = current_version + 1
        versions.append(
            TimelineVersion(
                project_id=timeline.project_id,
                version=next_version,
                timeline=timeline,
                change_summary=change_summary,
                affected_ids=affected_ids,
            )
        )
        updated = {
            "project_id": timeline.project_id,
            "current_version": next_version,
            "versions": [item.model_dump(mode="json") for item in versions],
        }
        try:
            reference.update(updated, option=firestore.LastUpdateOption(snapshot.update_time))
        except FailedPrecondition as error:
            raise TimelineVersionConflict("Timeline changed during this transaction.") from error
        return self._state(updated)

    def undo(self, project_id: str) -> TimelineHistoryState:
        return self._move(project_id, -1)

    def redo(self, project_id: str) -> TimelineHistoryState:
        return self._move(project_id, 1)

    def _move(self, project_id: str, delta: int) -> TimelineHistoryState:
        reference = self.collection.document(project_id)
        snapshot = reference.get()
        if not snapshot.exists:
            raise TimelineVersionConflict("Timeline history has not been initialized.")
        payload = _snapshot_data(snapshot)
        current_version = int(payload["current_version"])
        versions = [int(item["version"]) for item in payload["versions"]]
        target = current_version + delta
        if target not in versions:
            direction = "undo" if delta < 0 else "redo"
            raise TimelineVersionConflict(f"There is no timeline version to {direction}.")
        payload["current_version"] = target
        try:
            reference.update(payload, option=firestore.LastUpdateOption(snapshot.update_time))
        except FailedPrecondition as error:
            raise TimelineVersionConflict("Timeline changed during undo/redo.") from error
        return self._state(payload)


class FirestoreExportRepository:
    def __init__(self, client: firestore.Client) -> None:
        self.collection = client.collection("video_exports")

    def save(self, item: StoredExport) -> StoredExport:
        self.collection.document(item.export.id).set(
            {
                "export": item.export.model_dump(mode="json"),
                "file_path": item.file_path,
                "token_hash": item.token_hash,
            }
        )
        return item

    @staticmethod
    def _stored(payload: dict[str, Any]) -> StoredExport:
        return StoredExport(
            export=VideoExport.model_validate(payload["export"]),
            file_path=payload.get("file_path"),
            token_hash=payload.get("token_hash"),
        )

    def get(self, project_id: str, export_id: str) -> StoredExport | None:
        snapshot = self.collection.document(export_id).get()
        if not snapshot.exists:
            return None
        item = self._stored(_snapshot_data(snapshot))
        return item if item.export.project_id == project_id else None

    def latest_successful(self, project_id: str) -> StoredExport | None:
        candidates = [
            self._stored(_snapshot_data(snapshot))
            for snapshot in self.collection.stream()
        ]
        successful = [
            item
            for item in candidates
            if item.export.project_id == project_id and item.export.status == "succeeded"
        ]
        return max(successful, key=lambda item: item.export.created_at) if successful else None


@dataclass(frozen=True, slots=True)
class CloudTasksSettings:
    project_id: str
    location: str
    queue: str
    worker_url: str
    invoker_service_account: str

    @property
    def parent(self) -> str:
        return f"projects/{self.project_id}/locations/{self.location}/queues/{self.queue}"


class CloudTasksGateway(Protocol):
    def create_task(self, *, parent: str, task: dict[str, Any]) -> Any: ...


class CloudCaptureDispatcher:
    def __init__(self, client: CloudTasksGateway, settings: CloudTasksSettings) -> None:
        self.client = client
        self.settings = settings

    def dispatch(self, project_id: str, scene: Scene) -> str:
        body = json.dumps(
            {"project_id": project_id, "scene": scene.model_dump(mode="json")}
        ).encode()
        task: dict[str, Any] = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": f"{self.settings.worker_url.rstrip('/')}/tasks/capture",
                "headers": {"Content-Type": "application/json"},
                "body": body,
                "oidc_token": {
                    "service_account_email": self.settings.invoker_service_account,
                    "audience": self.settings.worker_url,
                },
            },
            "dispatch_deadline": "900s",
        }
        response = self.client.create_task(parent=self.settings.parent, task=task)
        return str(response.name)
