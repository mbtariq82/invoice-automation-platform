"""Prepare and monitor Cloud Deploy releases."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml


REQUIRED = (
    "GCP_PROJECT_ID", "GCP_REGION", "GCP_SERVICE", "GCP_MIGRATION_JOB",
    "GCP_IMAGE_REPOSITORY", "GCP_SERVICE_URL", "GCP_WORKLOAD_IDENTITY_PROVIDER",
    "GCP_DEPLOYER_SERVICE_ACCOUNT", "GCP_BUILD_SERVICE_ACCOUNT",
    "GCP_BUILD_SOURCE_BUCKET", "GCP_DELIVERY_PIPELINE",
)


def validate():
    missing = [name for name in REQUIRED if not os.environ.get(name, "").strip()]
    if missing:
        raise ValueError("Missing deployment variables: " + ", ".join(missing))
    if not os.environ["GCP_SERVICE_URL"].startswith("https://"):
        raise ValueError("GCP_SERVICE_URL must be HTTPS")
    if not os.environ["GCP_BUILD_SOURCE_BUCKET"].startswith("gs://"):
        raise ValueError("GCP_BUILD_SOURCE_BUCKET must be a gs:// URL")
    expected_suffix = "@" + os.environ["GCP_PROJECT_ID"] + ".iam.gserviceaccount.com"
    if not os.environ["GCP_BUILD_SERVICE_ACCOUNT"].endswith(expected_suffix):
        raise ValueError("GCP_BUILD_SERVICE_ACCOUNT must belong to the deployment project")


def gcloud(*args):
    result = subprocess.run(
        ["gcloud", *args, "--project=" + os.environ["GCP_PROJECT_ID"],
         "--region=" + os.environ["GCP_REGION"], "--quiet"],
        check=True, text=True, stdout=subprocess.PIPE,
    )
    return result.stdout


def prepare_manifest(path):
    manifest_path = Path(path)
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("apiVersion") != "serving.knative.dev/v1" or manifest.get("kind") != "Service":
        raise ValueError("Expected an exported Cloud Run Service manifest")
    if manifest.get("metadata", {}).get("name") != os.environ["GCP_SERVICE"]:
        raise ValueError("Exported manifest does not match GCP_SERVICE")

    manifest.pop("status", None)
    metadata = manifest["metadata"]
    for key in ("creationTimestamp", "generation", "managedFields", "namespace", "resourceVersion", "selfLink", "uid"):
        metadata.pop(key, None)
    manifest["spec"].pop("traffic", None)  # Cloud Deploy manages canary traffic.
    template_metadata = manifest["spec"]["template"].get("metadata", {})
    template_metadata.pop("creationTimestamp", None)
    template_metadata.pop("name", None)
    containers = manifest["spec"]["template"]["spec"]["containers"]
    if len(containers) != 1:
        raise ValueError("Cloud Deploy release expects one application container")
    containers[0]["image"] = "invoice-api"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")


def wait_for_rollout(release, timeout_seconds=1800, poll_seconds=10):
    deadline = time.monotonic() + timeout_seconds
    rollout = None
    last_state = None
    while time.monotonic() < deadline:
        if rollout is None:
            items = json.loads(gcloud(
                "deploy", "rollouts", "list",
                "--delivery-pipeline=" + os.environ["GCP_DELIVERY_PIPELINE"],
                "--release=" + release, "--format=json",
            ))
            if items:
                rollout = max(items, key=lambda item: item.get("createTime", ""))["name"].rsplit("/", 1)[-1]
        else:
            item = json.loads(gcloud(
                "deploy", "rollouts", "describe", rollout,
                "--delivery-pipeline=" + os.environ["GCP_DELIVERY_PIPELINE"],
                "--release=" + release, "--format=json",
            ))
            state = item["state"]
            if state != last_state:
                print(f"Cloud Deploy rollout {rollout}: {state}", flush=True)
                last_state = state
            if state == "SUCCEEDED":
                return
            if state in {"FAILED", "CANCELLED", "HALTED"}:
                raise RuntimeError(f"Cloud Deploy rollout ended in {state}")
        time.sleep(poll_seconds)
    raise TimeoutError("Timed out waiting for Cloud Deploy rollout")


def main():
    validate()
    command = sys.argv[1]
    if command == "validate":
        return
    if command == "prepare":
        prepare_manifest(sys.argv[2])
        return
    if command == "wait":
        wait_for_rollout(sys.argv[2])
        return
    raise ValueError("Unknown deployment command: " + command)


if __name__ == "__main__":
    main()
