"""Copy the running services to Veyframe and preserve their runtime data and IAM."""

import argparse
import copy
import json
import shutil
import subprocess
import time
from pathlib import Path

import httpx

PROJECT = "demodirector-507722"
REGION = "us-central1"
PARENT = f"projects/{PROJECT}/locations/{REGION}"
API = "https://run.googleapis.com/v2/"
ROLES = ("worker", "api", "web")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    cli = shutil.which("gcloud")
    if not cli:
        raise RuntimeError("Google Cloud CLI is required")
    token = subprocess.run(
        [cli, "auth", "print-access-token"], capture_output=True, text=True, check=True
    ).stdout.strip()
    client = httpx.Client(headers={"Authorization": f"Bearer {token}"}, timeout=120)

    def request(method: str, resource: str, **kwargs: object) -> dict:
        response = client.request(method, API + resource, **kwargs)
        if response.is_error:
            raise RuntimeError(f"Cloud Run {method} {resource}: HTTP {response.status_code}")
        return response.json()

    def wait(operation: dict) -> None:
        deadline = time.monotonic() + 600
        while not operation.get("done"):
            if time.monotonic() > deadline:
                raise RuntimeError(f"Operation still pending: {operation['name']}")
            time.sleep(3)
            operation = request("GET", operation["name"])
        if operation.get("error"):
            raise RuntimeError(f"Cloud Run operation failed with code {operation['error']['code']}")

    def service(name: str) -> dict:
        return request("GET", f"{PARENT}/services/{name}")

    def set_env(template: dict, changes: dict[str, str]) -> None:
        env = template["containers"][0].setdefault("env", [])
        for name, value in changes.items():
            env[:] = [entry for entry in env if entry["name"] != name]
            env.append({"name": name, "value": value})

    source = {role: service(f"demodirector-{role}") for role in ROLES}
    for role, old in source.items():
        print(json.dumps({"from": f"demodirector-{role}", "to": f"veyframe-{role}",
                          "source_url": old["uri"],
                          "source_revision": old["latestReadyRevision"]}), flush=True)
    if not args.apply:
        return

    target = {}
    for role in ROLES:
        name = f"veyframe-{role}"
        old = source[role]
        template = copy.deepcopy(old["template"])
        template.pop("revision", None)
        revision = request("GET", old["latestReadyRevision"])
        for container, running in zip(template["containers"], revision["containers"], strict=True):
            container["image"] = running["image"]
        if role == "api":
            set_env(template, {"DEMO_WORKER_URL": target["worker"]["uri"]})
        if role == "web":
            set_env(template, {"API_BASE_URL": target["api"]["uri"]})
        payload = {key: copy.deepcopy(old[key]) for key in (
            "description", "labels", "annotations", "ingress", "launchStage",
            "binaryAuthorization", "scaling", "invokerIamDisabled", "defaultUriDisabled",
        ) if key in old}
        payload["template"] = template
        payload["traffic"] = [{"type": "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST", "percent": 100}]
        print(f"Creating {name} from its running image", flush=True)
        wait(request("POST", f"{PARENT}/services", params={"serviceId": name}, json=payload))
        policy = request("GET", f"{old['name']}:getIamPolicy")
        policy.pop("etag", None)
        request("POST", f"{PARENT}/services/{name}:setIamPolicy", json={"policy": policy})
        target[role] = service(name)
        print(f"Ready: {target[role]['uri']}", flush=True)

    api = target["api"]
    template = copy.deepcopy(api["template"])
    template.pop("revision", None)
    env = {entry["name"]: entry.get("value", "") for entry in template["containers"][0]["env"]}
    origins = set(filter(None, env.get("DEMO_CAPTURE_AUTH_ORIGINS", "").split(",")))
    origins.add(target["web"]["uri"])
    origins.update(target["web"].get("urls", []))
    set_env(template, {"DEMO_GENERATION_TASK_URL": api["uri"],
                       "DEMO_CAPTURE_AUTH_ORIGINS": ",".join(sorted(origins))})
    print("Connecting Veyframe generation callbacks and capture origins", flush=True)
    wait(request("PATCH", api["name"], params={"updateMask": "template"},
                 json={"name": api["name"], "template": template}))
    target["api"] = service("veyframe-api")
    summary = {role: {"name": value["name"], "url": value["uri"],
                      "revision": value["latestReadyRevision"]} for role, value in target.items()}
    output = Path("artifacts/cloud-veyframe")
    output.mkdir(parents=True, exist_ok=True)
    (output / "services.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)
    client.close()


if __name__ == "__main__":
    main()
