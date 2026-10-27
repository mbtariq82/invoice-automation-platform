"""Release an existing Cloud Run service without managing infrastructure/state."""

import json
import os
import re
import subprocess
import sys
from urllib.request import Request, urlopen


REQUIRED = (
    "GCP_PROJECT_ID", "GCP_REGION", "GCP_SERVICE", "GCP_MIGRATION_JOB",
    "GCP_IMAGE_REPOSITORY", "GCP_SERVICE_URL", "GCP_WORKLOAD_IDENTITY_PROVIDER",
    "GCP_DEPLOYER_SERVICE_ACCOUNT", "GCP_BUILD_SERVICE_ACCOUNT",
    "GCP_BUILD_SOURCE_BUCKET",
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


def service():
    return json.loads(gcloud("run", "services", "describe", os.environ["GCP_SERVICE"], "--format=json"))


def smoke(url):
    token = os.environ["SMOKE_ID_TOKEN"]
    for path in ("/health", "/v1/invoices"):
        request = Request(url.rstrip("/") + path, headers={
            "Authorization": f"Bearer {token}",
            "X-API-Authorization": f"Bearer {token}",
        })
        with urlopen(request, timeout=30) as response:
            body = json.load(response)
            if response.status != 200 or (path == "/health" and body != {"status": "ok"}):
                raise RuntimeError("Smoke check failed: " + path)
            if path == "/v1/invoices" and not isinstance(body, list):
                raise RuntimeError("Invalid invoice-list response")
        print("Verified " + path, flush=True)


def migrate(image):
    gcloud("run", "jobs", "update", os.environ["GCP_MIGRATION_JOB"], "--image=" + image)
    gcloud("run", "jobs", "execute", os.environ["GCP_MIGRATION_JOB"], "--wait")


def rollout(image):
    current = service()
    canonical = current["status"]["url"]
    if canonical.rstrip("/") != os.environ["GCP_SERVICE_URL"].rstrip("/"):
        raise ValueError("Configured service URL does not match deployed service")
    traffic = [item for item in current["status"]["traffic"] if item.get("percent", 0) > 0]
    if len(traffic) != 1 or traffic[0]["percent"] != 100:
        raise ValueError("Deployment requires a single revision serving 100% of traffic")
    previous = json.loads(gcloud("run", "revisions", "describe", traffic[0]["revisionName"], "--format=json"))
    previous_image = previous["spec"]["containers"][0]["image"]
    tag = "ci-" + os.environ["GITHUB_RUN_ID"] + "-" + os.environ["GITHUB_RUN_ATTEMPT"]
    suffix = "gh-" + os.environ["GITHUB_SHA"][:12] + "-" + tag[3:]
    os.environ["SMOKE_ID_TOKEN"]  # Fail before changes if the token was not issued.
    try:
        gcloud("run", "services", "update", os.environ["GCP_SERVICE"],
               "--image=" + image, "--no-traffic", "--tag=" + tag, "--revision-suffix=" + suffix)
        candidate = next(item["url"] for item in service()["status"]["traffic"] if item.get("tag") == tag)
        smoke(candidate)
        gcloud("run", "services", "update-traffic", os.environ["GCP_SERVICE"], "--to-latest", "--remove-tags=" + tag)
        smoke(canonical)
    except Exception:
        print("Rollout failed; restoring the previous image as the latest revision", file=sys.stderr)
        # Restore the image too: leaving the failed image as LATEST would allow
        # a later Terraform apply to send traffic back to the failed release.
        gcloud("run", "services", "update", os.environ["GCP_SERVICE"], "--image=" + previous_image)
        flags = ["--to-latest"]
        if any(item.get("tag") == tag for item in service()["status"]["traffic"]):
            flags.append("--remove-tags=" + tag)
        gcloud("run", "services", "update-traffic", os.environ["GCP_SERVICE"], *flags)
        raise
    print("Deployed " + image, flush=True)


def main():
    validate()
    command = sys.argv[1]
    if command == "validate":
        return
    image = os.environ["RELEASE_IMAGE"]
    if not re.fullmatch(re.escape(os.environ["GCP_IMAGE_REPOSITORY"]) + r"/api@sha256:[a-f0-9]{64}", image):
        raise ValueError("Release must be a digest in the configured image repository")
    {"migrate": migrate, "rollout": rollout}[command](image)


if __name__ == "__main__":
    main()
