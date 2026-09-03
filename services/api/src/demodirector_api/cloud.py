from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

from demodirector_contracts import Project, Scene
from google.cloud import firestore, tasks_v2


class FirestoreProjectRepository:
    """Durable project metadata repository used by the Cloud Run API."""

    def __init__(self, client: firestore.Client) -> None:
        self.collection = client.collection("projects")

    def create(self, project: Project) -> Project:
        self.collection.document(project.id).create(project.model_dump(mode="json"))
        return project

    def get(self, project_id: str) -> Project | None:
        snapshot = self.collection.document(project_id).get()
        return None if not snapshot.exists else Project.model_validate(snapshot.to_dict())

    def update(self, project: Project) -> Project | None:
        reference = self.collection.document(project.id)
        if not reference.get().exists:
            return None
        reference.set(project.model_dump(mode="json"))
        return project

    def list(self, owner_user_id: str | None = None) -> list[Project]:
        projects = [
            Project.model_validate(snapshot.to_dict()) for snapshot in self.collection.stream()
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
