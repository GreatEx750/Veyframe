"""Exercise local Next proxies against serve-quality-fixture.py; no paid provider calls."""
import httpx

with httpx.Client(base_url="http://localhost:3100", timeout=120) as client:
    login = client.post("/api/auth/login", json={
        "email": "reviewer@example.test", "password": "fixture-password-only",
    })
    login.raise_for_status()
    base = "/api/projects/project-one-click"
    job = client.get(f"{base}/generation").json()
    assert job["status"] == "succeeded", job
    video = client.get(f"{base}/exports/latest").json()
    media = client.get(f"{base}/exports/{video['id']}/video")
    assert media.status_code == 200 and len(media.content) > 1000
    response = client.post(f"{base}/quality-api/exports/{video['id']}/reviews", json={})
    response.raise_for_status()
    review = response.json()
    assert review["status"] == "succeeded", review
    assert len(review["result"]["scores"]) == 6
    proposal_response = client.post(f"{base}/quality-api/optimizations", json={"review_id": review["id"]})
    proposal_response.raise_for_status()
    proposal = proposal_response.json()
    print({"job": job["status"], "video_bytes": len(media.content),
           "review": review["status"], "dimensions": len(review["result"]["scores"]),
           "proposed_operations": len(proposal["proposal"]["operations"]),
           "model": review["model_name"]})
    if proposal["proposal"]["operations"]:
        applied = client.post(f"{base}/quality-api/optimizations/{proposal['id']}/apply",
            json={"expected_version": proposal["before_version"], "approved": True})
        applied.raise_for_status()
        result = applied.json()
        assert result["status"] == "succeeded", result
        assert result["score_delta"] == 0
        assert client.get(f"{base}/exports/latest").json()["id"] == video["id"]
        print({"repair": result["status"], "stop_reason": result["stop_reason"],
               "original_preserved": True, "paid_calls": 0})
