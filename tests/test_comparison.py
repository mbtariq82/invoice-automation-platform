import json

import httpx
import pytest

from invoice_automation_platform.evaluation import compare


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    root = tmp_path / "corpus"
    root.mkdir()
    documents = []
    for name, category in (("clean-a", "clean"), ("clean-b", "clean"), ("hard-a", "hard")):
        data = name.encode()
        (root / f"{name}.pdf").write_bytes(data)
        documents.append({
            "doc_id": name, "file": f"{name}.pdf", "render": "pdf", "category": category,
            "sha256": compare.digest(data), "difficulty": "easy", "kind": "invoice",
            "expected": {"vendor_name": "Acme", "invoice_number": name, "total": 100,
                         "document_type": "invoice", "should_flag": category == "hard",
                         "scored": ["vendor_name", "invoice_number", "total", "document_type", "flag"]},
        })
    (root / "manifest.json").write_text(json.dumps({"documents": documents}))
    monkeypatch.setattr(compare, "extract_pdf_text", lambda path: path.stem)
    monkeypatch.setattr(compare.time, "sleep", lambda seconds: None)
    return root


def mock_handler(request):
    payload = json.loads(request.content)
    if request.url.path.endswith("decisions"):
        name = payload["state"]
        body = {"answers": {"document_type": {"choice": "invoice"},
                            "flagged": {"noul": .9 if name.startswith("hard") else .1}}}
    else:
        text = payload["messages"][1]["content"]
        name = text.split("\n\n")[-1]
        if "Extract the invoice fields" in text:
            prediction = {"vendor_name": "Acme", "invoice_number": name,
                          "total": 100, "document_type": "invoice", "lines": []}
        else:
            prediction = {"document_type": "invoice", "flagged": name.startswith("hard")}
        body = {"choices": [{"message": {"content": json.dumps(prediction)}, "finish_reason": "stop"}]}
    return httpx.Response(200, json={**body, "id": "generation-id", "model": payload["model"],
                                    "provider": "test-provider", "usage": {"cost": .01}})


def client(handler=mock_handler):
    return httpx.Client(base_url=compare.API_ROOT, transport=httpx.MockTransport(handler))


def test_dry_run_never_loads_credentials_or_writes_files(corpus, tmp_path, monkeypatch):
    def forbidden(*args):
        pytest.fail("dry run fetched credentials")
    monkeypatch.setattr(compare, "get_secret", forbidden)
    out = tmp_path / "results"
    plan = compare.run_comparison(corpus=corpus, out=out, limit=2, dry_run=True)
    assert not out.exists()
    assert plan["document_count"] == 2
    assert plan["maximum_requests"] == 42  # 7 tasks * 2 PDFs * 3 attempts
    assert list(plan["document_hashes"]) == ["clean-a", "hard-a"]
    assert len(plan["jobs"]) == 7
    assert not any(j["candidate"] == "jev" and j["task"] == "extraction" for j in plan["jobs"])


def test_full_comparison_and_resume(corpus, tmp_path):
    out = tmp_path / "results"
    with client() as transport:
        result = compare.run_comparison(corpus=corpus, out=out, limit=2, repeats=2,
                                        workers=2, client=transport)
    assert len(result["runs"]) == 14
    for row in result["runs"]:
        assert row["scores"]["summary"]["fully_correct"] == 2
        assert row["scores"]["operational"]["known_cost_usd"] == .02
        assert row["scores"]["operational"]["cost_complete"] is True
    assert len(result["paired"]) == 18  # 3 extraction pairs + 6 decision pairs, per repeat
    assert (out / "jev/decisions/repeat-1/documents/hard-a.json").exists()
    assert not (out / "jev/extraction").exists()
    assert "Jev has no extraction score" in (out / "comparison.md").read_text()
    def forbidden(request):
        pytest.fail("resume repeated a completed request")
    with client(forbidden) as transport:
        resumed = compare.run_comparison(corpus=corpus, out=out, limit=2, repeats=2,
                                         workers=2, resume=True, client=transport)
    assert resumed == result
    with client() as transport, pytest.raises(ValueError, match="configuration changed"):
        compare.run_comparison(corpus=corpus, out=out, limit=1, resume=True, client=transport)


def test_failure_remains_in_denominator_and_cost_unknown(corpus, tmp_path):
    def failure(request):
        if "hard-a" in request.content.decode():
            return httpx.Response(429, json={"error": "rate limited"})
        return mock_handler(request)
    with client(failure) as transport:
        result = compare.run_comparison(corpus=corpus, out=tmp_path / "results", limit=2,
                                        names=["jev"], retries=1, client=transport)
    row = result["runs"][0]
    summary, op = row["scores"]["summary"], row["scores"]["operational"]
    assert summary["documents"] == 2
    assert summary["fully_correct"] == 1
    assert summary["flag_recall"] == 0
    assert op["failed_documents"] == 1
    assert op["attempts"] == 3
    assert op["known_cost_usd"] == .01
    assert op["cost_complete"] is False
    assert op["cost_per_correct_invoice_usd"] is None


def test_extraction_failure_is_scored_as_wrong(corpus, tmp_path):
    def failure(request):
        return httpx.Response(401)
    with client(failure) as transport:
        result = compare.run_comparison(corpus=corpus, out=tmp_path / "results", limit=2,
                                        names=["openai"], task="extraction", client=transport)
    row = result["runs"][0]
    assert row["scores"]["summary"]["documents_without_prediction"] == 2
    assert row["scores"]["summary"]["fully_correct"] == 0
    assert row["scores"]["operational"]["attempts"] == 2  # authentication errors aren't retried


def test_invalid_output_retry_preserves_both_bills():
    count = 0
    def handler(request):
        nonlocal count
        count += 1
        response = mock_handler(request)
        if count == 1:
            body = json.loads(response.content)
            body["choices"][0]["message"]["content"] = "invalid json"
            return httpx.Response(200, json=body)
        return response
    with client(handler) as transport:
        result = compare.perform(transport, compare.read_candidates(compare.DEFAULT_CONFIG)[0],
                                 "extraction", "clean-a", retries=1, max_tokens=100, threshold=.5)
    metrics = compare.operational_metrics({"clean-a": result}, 1, 1)
    assert metrics["known_cost_usd"] == .02
    assert metrics["invalid_response_attempts"] == 1
    assert result["prediction"]["invoice_number"] == "clean-a"


def test_changed_document_hash_rejected(corpus, tmp_path):
    (corpus / "clean-a.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        compare.run_comparison(corpus=corpus, out=tmp_path / "results", dry_run=True)


def test_jev_request_and_threshold():
    candidate = compare.read_candidates(compare.DEFAULT_CONFIG, ["jev"])[0]
    endpoint, payload = compare.make_request(candidate, "decisions", "invoice text", 100)
    assert endpoint == "alpha/decisions"
    assert payload["model"] == "typesafe/jev-1.14"
    assert "expected" not in payload
    body = {"answers": {"document_type": {"choice": "other"}, "flagged": {"noul": .6}}}
    assert compare.parse_response(candidate, "decisions", body, .7)["flagged"] is False
    with pytest.raises(ValueError, match="not invoice field extraction"):
        compare.make_request(candidate, "extraction", "text", 100)
    body["answers"]["flagged"]["noul"] = float("nan")
    with pytest.raises(ValueError, match="probability"):
        compare.parse_response(candidate, "decisions", body, .5)


def test_config_validation_and_no_output_overwrite(corpus, tmp_path):
    with pytest.raises(ValueError):
        compare.Candidate(name="../escape", model="model", api="chat")
    with pytest.raises(ValueError):
        compare.Candidate(name="x", model="model", api="chat", parameters={"model": "other"})
    out = tmp_path / "results"
    out.mkdir()
    (out / "keep.txt").write_text("keep")
    with pytest.raises(ValueError, match="empty"):
        compare.run_comparison(corpus=corpus, out=out)


def test_decision_json_boolean_is_strict():
    candidate = compare.read_candidates(compare.DEFAULT_CONFIG)[0]
    body = {"choices": [{"message": {"content": '{"document_type":"invoice","flagged":"false"}'},
                          "finish_reason": "stop"}]}
    with pytest.raises(ValueError):
        compare.parse_response(candidate, "decisions", body, .5)


def test_chat_candidates_share_strict_schema():
    candidates = [c for c in compare.read_candidates(compare.DEFAULT_CONFIG) if c.api == "chat"]
    for task in ("extraction", "decisions"):
        formats = [compare.make_request(c, task, "text", 100)[1]["response_format"] for c in candidates]
        assert formats[0] == formats[1] == formats[2]
        assert formats[0]["json_schema"]["strict"] is True
        assert formats[0]["json_schema"]["schema"]["additionalProperties"] is False
