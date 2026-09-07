"""Durable timings for actual authored-pipeline calls, not inferred activity labels."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import TypeVar

from demodirector_contracts.jobs import (
    GenerationJob,
    GenerationTrace,
    GenerationTraceStage,
    StageContribution,
    TraceStageKind,
)

from demodirector_api.records import RecordStore

T = TypeVar("T")


class PresentationTraceRecorder:
    def __init__(self, records: RecordStore, job: GenerationJob) -> None:
        self.records, self.job = records, job
        self.key = f"presentation-trace-{job.id}"

    def read(self) -> GenerationTrace:
        saved = self.records.get(self.key)
        if saved:
            trace = GenerationTrace.model_validate(saved[1])
            if trace.project_id != self.job.project_id or trace.job_id != self.job.id:
                raise ValueError("Foreign presentation trace")
            return trace
        return GenerationTrace(
            id=f"trace-{self.job.id}", project_id=self.job.project_id, job_id=self.job.id,
            status="running", created_at=self.job.created_at, updated_at=self.job.updated_at,
            stages=[],
        )

    def save(self, trace: GenerationTrace) -> None:
        saved = self.records.get(self.key)
        self.records.put(self.key, saved[0] if saved else 0, trace.model_dump(mode="json"))

    def describe_last(
        self, message: str, contributions: list[StageContribution], *, failed: bool = False,
    ) -> None:
        trace = self.read()
        stage = GenerationTraceStage.model_validate({
            **trace.stages[-1].model_dump(), "message": message,
            "contributions": contributions,
            **({"status": "failed"} if failed else {}),
        })
        self.save(trace.model_copy(update={"stages": [*trace.stages[:-1], stage]}))

    def call(self, kind: TraceStageKind, label: str, service: str, fn: Callable[[], T]) -> T:
        trace = self.read()
        started = datetime.now(UTC)
        sequence = len(trace.stages) + 1
        stage = GenerationTraceStage(
            id=f"{kind}-{sequence}", project_id=self.job.project_id, kind=kind,
            sequence=sequence, attempt=self.job.attempts, retry_count=self.job.attempts - 1,
            status="running", label=label, service=service, started_at=started,
            message="Executing the configured component; elapsed time includes local validation.",
        )
        trace = trace.model_copy(update={"stages": [*trace.stages, stage],
                                        "status": "running", "updated_at": started})
        self.save(trace)
        failed = False
        try:
            result = fn()
            failed = getattr(result, "status", None) == "failed"
            return result
        except Exception:
            failed = True
            raise
        finally:
            ended = datetime.now(UTC)
            completed = stage.model_copy(update={
                "status": "failed" if failed else "succeeded", "completed_at": ended,
                "elapsed_ms": max(0, round((ended - started).total_seconds() * 1000)),
                "message": "Component failed; see job details." if failed else
                "Component returned successfully. Timing includes validation and local work.",
            })
            self.save(trace.model_copy(update={
                "stages": [*trace.stages[:-1], completed], "updated_at": ended,
                "status": "failed" if failed else "running",
            }))


def recorded_call[T](
    recorder: PresentationTraceRecorder | None,
    kind: TraceStageKind,
    label: str,
    service: str,
    fn: Callable[[], T],
) -> T:
    return recorder.call(kind, label, service, fn) if recorder else fn()
