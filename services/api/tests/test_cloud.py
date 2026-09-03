from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from demodirector_api.cloud import (
    CloudCaptureDispatcher,
    CloudTasksSettings,
    FirestoreProjectRepository,
)
from demodirector_contracts import CapturePlan, Project, Scene
from pydantic import HttpUrl


class Snapshot:
    def __init__(self, value: dict[str, Any] | None) -> None:
        self.value = value
        self.exists = value is not None

    def to_dict(self) -> dict[str, Any]:
        assert self.value is not None
        return self.value


class Document:
    def __init__(self, values: dict[str, dict[str, Any]], key: str) -> None:
        self.values = values
        self.key = key

    def create(self, value: dict[str, Any]) -> None:
        self.values[self.key] = value

    def get(self) -> Snapshot:
        return Snapshot(self.values.get(self.key))

    def set(self, value: dict[str, Any]) -> None:
        self.values[self.key] = value


class Collection:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, Any]] = {}

    def document(self, key: str) -> Document:
        return Document(self.values, key)

    def stream(self) -> list[Snapshot]:
        return [Snapshot(value) for value in self.values.values()]


class FirestoreClient:
    def __init__(self) -> None:
        self.projects = Collection()

    def collection(self, name: str) -> Collection:
        assert name == "projects"
        return self.projects


def project(project_id: str, updated_at: datetime) -> Project:
    return Project(
        id=project_id,
        name=f"Project {project_id}",
        website_url=HttpUrl("https://example.com"),
        product_summary="A deterministic product fixture",
        audience="Product teams",
        tone="clear",
        requested_duration_seconds=60,
        cta="Try it",
        status="draft",
        job_status="idle",
        created_at=updated_at,
        updated_at=updated_at,
    )


def scene() -> Scene:
    return Scene(
        id="scene-1",
        storyboard_id="storyboard-1",
        order=0,
        title="Dashboard",
        objective="Show dashboard",
        narration="Review the dashboard.",
        capture_plan=CapturePlan(
            start_url=HttpUrl("https://example.com"),
            actions=[],
            success_assertions=[],
            timeout_seconds=30,
        ),
        duration_seconds=5,
    )


def test_firestore_project_repository_persists_and_lists_newest_first() -> None:
    client = FirestoreClient()
    repository = FirestoreProjectRepository(client)  # type: ignore[arg-type]
    now = datetime.now(UTC)
    older = repository.create(project("older", now - timedelta(minutes=1)))
    newer = repository.create(project("newer", now))

    assert repository.get(older.id) == older
    assert [item.id for item in repository.list()] == [newer.id, older.id]
    assert repository.update(newer.model_copy(update={"name": "Renamed"})).name == "Renamed"  # type: ignore[union-attr]
    assert repository.update(project("missing", now)) is None


class TasksClient:
    def __init__(self) -> None:
        self.parent = ""
        self.task: dict[str, Any] = {}

    def create_task(self, *, parent: str, task: dict[str, Any]) -> SimpleNamespace:
        self.parent = parent
        self.task = task
        return SimpleNamespace(name=f"{parent}/tasks/task-1")


def test_capture_dispatcher_uses_private_oidc_worker_task() -> None:
    client = TasksClient()
    settings = CloudTasksSettings(
        project_id="habiwatch",
        location="us-central1",
        queue="demodirector-jobs",
        worker_url="https://worker.example",
        invoker_service_account="tasks@habiwatch.iam.gserviceaccount.com",
    )
    dispatcher = CloudCaptureDispatcher(client, settings)

    name = dispatcher.dispatch("project-1", scene())

    request = client.task["http_request"]
    assert name.endswith("/tasks/task-1")
    assert client.parent == settings.parent
    assert request["url"] == "https://worker.example/tasks/capture"
    assert request["oidc_token"]["service_account_email"].startswith("tasks@")
    assert json.loads(request["body"])["project_id"] == "project-1"
