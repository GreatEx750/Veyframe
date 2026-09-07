from datetime import UTC, datetime
from pathlib import Path

import pytest
from demodirector_api.presentation_trace import PresentationTraceRecorder
from demodirector_api.records import SQLiteRecordStore
from demodirector_contracts.jobs import GenerationJob


def test_trace_records_real_calls_and_preserves_failure(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    job = GenerationJob(id="job", project_id="project", status="running", stage="storyboard",
                        attempts=1, version=1, created_at=now, updated_at=now,
                        message="Writing slide")
    recorder = PresentationTraceRecorder(SQLiteRecordStore(tmp_path / "trace.db"), job)
    assert recorder.call("storyboard", "Slide 1 copy", "Google ADK / Gemini", lambda: 42) == 42
    trace = recorder.read()
    assert trace.stages[0].status == "succeeded"
    assert trace.stages[0].elapsed_ms is not None

    def failure() -> None:
        raise RuntimeError("secret=not-for-the-ui")

    with pytest.raises(RuntimeError):
        recorder.call("narration", "Slide 1 speech", "Gemini TTS", failure)
    trace = recorder.read()
    assert trace.stages[-1].status == "failed"
    assert "secret=" not in trace.model_dump_json()
    assert trace.status == "failed"
