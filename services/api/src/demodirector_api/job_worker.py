"""Run alongside the local API: python -m demodirector_api.job_worker."""
import time

from demodirector_api.generation_jobs import GenerationJobs


def main() -> None:
    from demodirector_api.main import app
    jobs: GenerationJobs | None = app.state.generation_jobs
    if jobs is None:
        raise RuntimeError("Configure the local generation runtime first.")
    while True:
        if not jobs.local_tick():
            time.sleep(2)


if __name__ == "__main__":
    main()
