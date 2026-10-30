import importlib.util
import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("deploy", ROOT / "scripts" / "deploy.py")
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


@pytest.fixture(autouse=True)
def deployment_environment(monkeypatch):
    values = {
        "GCP_PROJECT_ID": "invoice-project",
        "GCP_REGION": "europe-west2",
        "GCP_SERVICE": "invoice-dev-api",
        "GCP_MIGRATION_JOB": "invoice-dev-migrate",
        "GCP_IMAGE_REPOSITORY": "europe-west2-docker.pkg.dev/invoice-project/images",
        "GCP_SERVICE_URL": "https://api.example.run.app",
        "GCP_WORKLOAD_IDENTITY_PROVIDER": "projects/1/locations/global/workloadIdentityPools/github/providers/github",
        "GCP_DEPLOYER_SERVICE_ACCOUNT": "deployer@invoice-project.iam.gserviceaccount.com",
        "GCP_BUILD_SERVICE_ACCOUNT": "builder@invoice-project.iam.gserviceaccount.com",
        "GCP_BUILD_SOURCE_BUCKET": "gs://invoice-build-source",
        "GCP_DELIVERY_PIPELINE": "invoice-dev-api",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def exported_service():
    return {
        "apiVersion": "serving.knative.dev/v1",
        "kind": "Service",
        "metadata": {
            "name": "invoice-dev-api",
            "namespace": "invoice-project",
            "uid": "read-only",
            "labels": {"cloud.googleapis.com/location": "europe-west2"},
        },
        "spec": {
            "template": {
                "metadata": {
                    "name": "invoice-dev-api-old",
                    "annotations": {"autoscaling.knative.dev/minScale": "1"},
                },
                "spec": {
                    "serviceAccountName": "runtime@invoice-project.iam.gserviceaccount.com",
                    "containers": [{
                        "image": "old@sha256:" + "a" * 64,
                        "env": [{"name": "DATABASE_PASSWORD", "valueFrom": {"secretKeyRef": {"name": "db", "key": "latest"}}}],
                        "resources": {"limits": {"cpu": "1", "memory": "512Mi"}},
                    }],
                },
            },
            "traffic": [{"latestRevision": True, "percent": 100}],
        },
        "status": {"url": "https://api.example.run.app"},
    }


def test_prepare_preserves_runtime_configuration_and_removes_server_fields(tmp_path):
    path = tmp_path / "service.yaml"
    path.write_text(yaml.safe_dump(exported_service()), encoding="utf-8")

    deploy.prepare_manifest(path)

    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert "status" not in manifest
    assert "namespace" not in manifest["metadata"]
    assert "uid" not in manifest["metadata"]
    assert "traffic" not in manifest["spec"]
    assert "name" not in manifest["spec"]["template"]["metadata"]
    container = manifest["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == "invoice-api"
    assert container["env"][0]["valueFrom"]["secretKeyRef"]["name"] == "db"
    assert manifest["spec"]["template"]["metadata"]["annotations"]["autoscaling.knative.dev/minScale"] == "1"


def test_prepare_rejects_a_different_service(tmp_path):
    manifest = exported_service()
    manifest["metadata"]["name"] = "other"
    path = tmp_path / "service.yaml"
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="does not match"):
        deploy.prepare_manifest(path)


def test_wait_tracks_the_created_rollout_until_success(monkeypatch):
    responses = iter([
        json.dumps([{"name": "projects/p/rollouts/rollout-1", "createTime": "2026-01-01T00:00:00Z"}]),
        json.dumps({"state": "IN_PROGRESS"}),
        json.dumps({"state": "SUCCEEDED"}),
    ])
    calls = []
    monkeypatch.setattr(deploy, "gcloud", lambda *args: calls.append(args) or next(responses))
    monkeypatch.setattr(deploy.time, "sleep", lambda _: None)

    deploy.wait_for_rollout("release-1", timeout_seconds=10, poll_seconds=0)

    assert calls[0][:4] == ("deploy", "rollouts", "list", "--delivery-pipeline=invoice-dev-api")
    assert calls[-1][:4] == ("deploy", "rollouts", "describe", "rollout-1")


def test_wait_reports_failed_rollout(monkeypatch):
    responses = iter([
        json.dumps([{"name": "projects/p/rollouts/rollout-1"}]),
        json.dumps({"state": "FAILED"}),
    ])
    monkeypatch.setattr(deploy, "gcloud", lambda *args: next(responses))
    monkeypatch.setattr(deploy.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="FAILED"):
        deploy.wait_for_rollout("release-1", timeout_seconds=10, poll_seconds=0)


def test_validate_requires_project_build_identity(monkeypatch):
    deploy.validate()
    monkeypatch.setenv("GCP_BUILD_SERVICE_ACCOUNT", "builder@other-project.iam.gserviceaccount.com")
    with pytest.raises(ValueError, match="deployment project"):
        deploy.validate()


def test_cloud_build_pushes_the_substituted_image():
    config = yaml.safe_load((ROOT / "cloudbuild.yaml").read_text(encoding="utf-8"))
    assert config["images"] == ["${_IMAGE}"]
    assert config["options"]["logging"] == "CLOUD_LOGGING_ONLY"
    assert "@sha256:" in config["steps"][0]["name"]



def test_skaffold_defines_cloud_run_and_idempotent_migration_hook():
    config = yaml.safe_load((ROOT / "deploy" / "skaffold.yaml").read_text(encoding="utf-8"))
    assert config["manifests"]["rawYaml"] == ["service.yaml"]
    assert config["deploy"] == {"cloudrun": {}}
    migrate = config["customActions"][0]
    assert migrate["name"] == "migrate"
    script = migrate["containers"][0]["args"][-1]
    assert "gcloud run jobs update" in script
    assert "gcloud run jobs execute" in script
