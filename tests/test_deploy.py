import json
import subprocess
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("deploy", Path(__file__).resolve().parents[1] / "scripts" / "deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)

URL = "https://api.example.run.app"
IMAGE = "europe-west2-docker.pkg.dev/project/images/api@sha256:" + "a" * 64
OLD_IMAGE = "europe-west2-docker.pkg.dev/project/images/api@sha256:" + "b" * 64


@pytest.fixture
def release(monkeypatch):
    monkeypatch.setenv("GCP_SERVICE_URL", URL)
    monkeypatch.setenv("GCP_SERVICE", "invoice-api")
    monkeypatch.setenv("GCP_MIGRATION_JOB", "invoice-migrate")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_SHA", "c" * 40)
    monkeypatch.setenv("SMOKE_ID_TOKEN", "test-token")
    events = []
    active = {"status": {"url": URL, "traffic": [{"percent": 100, "revisionName": "old"}]}}
    candidate = {"status": {"traffic": [{"tag": "ci-123-1", "url": "https://candidate.run.app"}]}}
    snapshots = iter([active, candidate, candidate])

    def cloud(*args):
        events.append(("cloud", args))
        if args[:3] == ("run", "services", "describe"):
            return json.dumps(next(snapshots))
        if args[:3] == ("run", "revisions", "describe"):
            return json.dumps({"spec": {"containers": [{"image": OLD_IMAGE}]}})
        return ""

    monkeypatch.setattr(deploy, "gcloud", cloud)
    monkeypatch.setattr(deploy, "smoke", lambda url: events.append(("smoke", url)))
    return events


def test_candidate_is_verified_before_promotion(release):
    deploy.rollout(IMAGE)
    stage = next(i for i, event in enumerate(release) if event[0] == "cloud" and "--no-traffic" in event[1])
    probe = release.index(("smoke", "https://candidate.run.app"))
    promote = next(i for i, event in enumerate(release) if event[0] == "cloud" and "--to-latest" in event[1])
    assert stage < probe < promote < release.index(("smoke", URL))


@pytest.mark.parametrize("failed_url", ["https://candidate.run.app", URL])
def test_failed_smoke_restores_previous_image_and_latest_traffic(release, monkeypatch, failed_url):
    def failing_smoke(url):
        if url == failed_url:
            raise RuntimeError("Smoke failed")

    monkeypatch.setattr(deploy, "smoke", failing_smoke)
    with pytest.raises(RuntimeError, match="Smoke failed"):
        deploy.rollout(IMAGE)
    updates = [event[1] for event in release if event[0] == "cloud" and event[1][:3] == ("run", "services", "update")]
    assert "--image=" + OLD_IMAGE in updates[-1]
    assert "--to-latest" in release[-1][1]
    assert "--remove-tags=ci-123-1" in release[-1][1]


def test_migration_failure_stops_release(release, monkeypatch):
    calls = []

    def failed_migration(*args):
        calls.append(args)
        if args[:3] == ("run", "jobs", "execute"):
            raise subprocess.CalledProcessError(1, "gcloud")
        return ""

    monkeypatch.setattr(deploy, "gcloud", failed_migration)
    with pytest.raises(subprocess.CalledProcessError):
        deploy.migrate(IMAGE)
    assert [call[:3] for call in calls] == [("run", "jobs", "update"), ("run", "jobs", "execute")]


def test_wrong_service_url_is_rejected_before_updates(release, monkeypatch):
    monkeypatch.setenv("GCP_SERVICE_URL", "https://wrong.run.app")
    with pytest.raises(ValueError, match="does not match"):
        deploy.rollout(IMAGE)
    assert len(release) == 1
