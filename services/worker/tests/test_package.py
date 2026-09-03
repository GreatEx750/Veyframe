import demodirector_worker


def test_worker_package_exposes_its_version() -> None:
    assert demodirector_worker.__version__ == "0.1.0"

