import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from benchserver.api.app import create_app
from benchserver.cli import openapi_document
from benchserver.config import ROOT

from .conftest import drain, make_ctx, make_settings

SECRET_KEY = "sk-or-v1-THIS-IS-A-TEST-SECRET-0123456789"
SECRET_TOKEN = "operator-token-TEST-SECRET-abcdef"


def client_for(ctx) -> TestClient:
    return TestClient(create_app(ctx))


@pytest.fixture
def client(ctx):
    with client_for(ctx) as c:
        yield c


def _spec(**kw):
    return {"model_id": "mock/optimal", "profile_id": "standard", "mode": "quick_check",
            "spend_limit_usd": 5, "concurrency": 4, **kw}


def test_meta_health_and_read_endpoints(client):
    assert client.get("/api/health").json()["status"] == "ok"
    meta = client.get("/api/meta").json()
    assert meta["suite"]["version"] == "suite-1" and meta["suite"]["benchmarks"] == ["shadow_twins"]
    assert {p["pack_id"] for p in meta["packs"]} >= {"shadowtwins-practice-v1", "shadowtwins-ranked-v1"}
    assert [p["id"] for p in meta["profiles"]] == ["standard", "reasoning-low", "reasoning-high"]
    assert meta["providers"]["mock"]["enabled"] and not meta["providers"]["openrouter"]["configured"]
    r = client.get("/api/ready")
    assert r.status_code == 503 and r.json()["checks"]["worker"]["alive"] == 0  # no worker yet
    assert len(client.get("/api/packs/shadowtwins-ranked-v1").json()["items"]) == 30
    assert r.headers["x-content-type-options"] == "nosniff"


def test_catalog_compat_favorites_and_estimate(client):
    cat = client.get("/api/catalog").json()
    ids = {m["model_id"] for m in cat["models"]}
    assert "mock/optimal" in ids and cat["snapshots"]["mock"]["model_count"] == len(ids)
    reasoner = next(m for m in cat["models"] if m["model_id"] == "mock/reasoner")
    assert all(c["compatible"] for c in reasoner["compat"])
    plain = next(m for m in cat["models"] if m["model_id"] == "mock/optimal")
    assert {c["profile_id"]: c["compatible"] for c in plain["compat"]} == {
        "standard": True, "reasoning-low": False, "reasoning-high": False}
    assert client.put("/api/favorites", json={"model_id": "mock/optimal", "favorite": True}).json()["favorites"] == ["mock/optimal"]
    assert client.get("/api/catalog?q=reason").json()["models"][0]["model_id"] == "mock/reasoner"
    eps = client.get("/api/catalog/endpoints", params={"model_id": "mock/optimal"}).json()
    assert eps["endpoints"][0]["slug"] == "mock-endpoint"
    est = client.post("/api/runs/estimate", json=_spec(mode="standard", provider="mock-endpoint")).json()
    assert est["estimate"]["calls"] == 30 and est["estimate"]["worst_case_usd"] > est["estimate"]["typical_usd"]
    assert est["blocking"] == [] and est["not_ranked_reasons"] == ["mock provider (test double)"]
    bad = client.post("/api/runs/estimate", json=_spec(profile_id="reasoning-high")).json()
    assert any("reasoning" in b for b in bad["blocking"])
    unpriced = client.post("/api/runs/estimate", json=_spec(model_id="mock/unpriced")).json()
    assert any("pricing is unknown" in b for b in unpriced["blocking"])


def test_run_lifecycle_over_http(ctx, client):
    r = client.post("/api/runs", json=_spec())
    assert r.status_code == 201
    run = r.json()
    assert run["state"] == "active" and run["scores"]["scheduled"] == 9
    drain(ctx)
    run = client.get(f"/api/runs/{run['run_id']}").json()
    assert run["state"] == "completed" and run["scores"]["overall"] == 100.0
    items = client.get(f"/api/runs/{run['run_id']}/items").json()
    assert len(items) == 9 and all(i["score"] == 100.0 and i["valid"] for i in items)
    detail = client.get(f"/api/runs/{run['run_id']}/items/{items[0]['job_id']}").json()
    assert detail["prompt"]["messages"][0]["content"].startswith("Shadow Twins puzzle.")
    assert detail["attempts"][0]["content"] and detail["evaluation"]["valid"]
    rep = client.get(f"/api/instances/{items[0]['instance_id']}/replay",
                     params={"run_id": run["run_id"], "job_id": items[0]["job_id"]}).json()
    assert rep["model"]["score"] == 100.0 and rep["optimal"]["raw_objective"] == rep["model"]["raw_objective"]
    csv_text = client.get(f"/api/runs/{run['run_id']}/export?format=csv").text
    assert csv_text.splitlines()[0].startswith("run_id,model_id") and len(csv_text.splitlines()) == 10
    re = client.get(f"/api/runs/{run['run_id']}/reevaluate").json()
    assert re["mismatches"] == [] and re["aggregate_matches"]
    assert client.post(f"/api/runs/{run['run_id']}/actions/pause").status_code == 409
    assert client.post(f"/api/runs/{run['run_id']}/actions/explode").status_code == 400
    assert client.get("/api/runs/nope").status_code == 404
    listed = client.get("/api/runs").json()
    assert listed[0]["run_id"] == run["run_id"]
    detail = client.get("/api/models/detail", params={"model_id": "mock/optimal"}).json()
    assert detail["runs"][0]["run_id"] == run["run_id"] and detail["latest_eligible"] == []
    assert client.get("/api/leaderboard").json()["rows"] == []


def _read_sse(client, url, headers=None):
    events = []
    with client.stream("GET", url, headers=headers or {}) as resp:
        assert resp.headers["content-type"].startswith("text/event-stream")
        cur = {}
        for line in resp.iter_lines():
            if not line:
                if cur:
                    events.append(cur)
                    cur = {}
                continue
            if line.startswith(":") or line.startswith("retry:"):
                continue
            k, _, v = line.partition(": ")
            cur[k] = v
    return events


def test_sse_snapshot_and_resume(ctx, client):
    run_id = client.post("/api/runs", json=_spec()).json()["run_id"]
    drain(ctx)
    full = _read_sse(client, f"/api/runs/{run_id}/events")
    assert full[0]["event"] == "snapshot" and json.loads(full[0]["data"])["state"] == "completed"
    assert full[-1]["event"] == "end"
    everything = _read_sse(client, f"/api/runs/{run_id}/events?after=0")
    typed = [e for e in everything if e["event"] not in ("end",)]
    assert typed[0]["event"] == "run_created" and sum(e["event"] == "job_completed" for e in typed) == 9
    mid = int(typed[5]["id"])
    resumed = _read_sse(client, f"/api/runs/{run_id}/events", headers={"Last-Event-ID": str(mid)})
    ids = [int(e["id"]) for e in resumed if e["event"] != "end"]
    assert ids and min(ids) > mid and ids == [int(e["id"]) for e in typed if int(e["id"]) > mid]


def test_practice_mode_is_separate_and_hides_answers(client):
    practice = client.get("/api/practice").json()
    assert len(practice) == 9 and {p["pack_id"] for p in practice} == {"shadowtwins-practice-v1"}
    iid = practice[0]["instance_id"]
    hidden = client.get(f"/api/instances/{iid}").json()
    assert "hidden" in hidden["certificate"] and hidden["split"] == "practice"
    revealed = client.get(f"/api/instances/{iid}?reveal=true").json()
    w = revealed["certificate"]["core"]["best_witness"]
    out = client.post(f"/api/practice/{iid}/submit", json={"remove": w["remove"], "add": w["add"]}).json()
    assert out["unranked"] and out["evaluation"]["score"] == 100.0 and out["replay"]["model"]["label"] == "model"
    assert client.post(f"/api/practice/{iid}/submit", json={"remove": [True], "add": [0]}).status_code == 422
    ranked = client.get("/api/packs/shadowtwins-ranked-v1").json()["items"][0]["instance_id"]
    assert client.post(f"/api/practice/{ranked}/submit", json={"remove": [], "add": []}).status_code == 404


def test_body_limit(client):
    r = client.post("/api/runs/estimate", content=b"{" + b" " * 70_000 + b"}",
                    headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_auth_modes(tmp_path):
    ctx = make_ctx(make_settings(tmp_path, auth_mode="token", operator_token=SECRET_TOKEN))
    with client_for(ctx) as c:
        assert c.post("/api/runs", json=_spec()).status_code == 401
        assert c.post("/api/runs", json=_spec(), headers={"Authorization": "Bearer nope"}).status_code == 401
        ok = c.post("/api/runs", json=_spec(), headers={"Authorization": f"Bearer {SECRET_TOKEN}"})
        assert ok.status_code == 201
        assert c.get("/api/runs").status_code == 200  # reads stay public
        assert c.get("/api/meta").json()["auth"]["operator"] is False
        assert c.get("/api/meta", headers={"Authorization": f"Bearer {SECRET_TOKEN}"}).json()["auth"]["operator"]
    ro = make_ctx(make_settings(tmp_path / "ro", auth_mode="readonly"))
    with client_for(ro) as c:
        assert c.post("/api/runs", json=_spec()).status_code == 403
    local = make_ctx(make_settings(tmp_path / "local", auth_mode="local"))
    with client_for(local) as c:  # TestClient is not a loopback address
        r = c.post("/api/runs", json=_spec())
        assert r.status_code == 403 and "ST_OPERATOR_TOKEN" in r.json()["detail"]


def test_secrets_never_leave_the_server(tmp_path, caplog):
    settings = make_settings(tmp_path, auth_mode="token", operator_token=SECRET_TOKEN, openrouter_api_key=SECRET_KEY)
    ctx = make_ctx(settings)
    hdr = {"Authorization": f"Bearer {SECRET_TOKEN}"}
    with client_for(ctx) as c:
        run_id = c.post("/api/runs", json=_spec(), headers=hdr).json()["run_id"]
        drain(ctx)
        bodies = [c.get(p, headers=hdr).text for p in (
            "/api/meta", f"/api/runs/{run_id}", f"/api/runs/{run_id}/items", "/api/catalog",
            f"/api/runs/{run_id}/export?format=json", f"/api/runs/{run_id}/export?format=csv",
            f"/api/runs/{run_id}/events?after=0", "/api/openapi.json")]
    conn = ctx.connect()
    try:
        dump = "\n".join(conn.iterdump())
    finally:
        conn.close()
    logs = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "logs").glob("*.log")) if (tmp_path / "logs").exists() else ""
    for blob in [*bodies, dump, logs, caplog.text, repr(settings)]:
        assert SECRET_KEY not in blob and SECRET_TOKEN not in blob


def test_committed_openapi_matches_app():
    committed = json.loads((ROOT / "contracts" / "openapi.json").read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(openapi_document(), sort_keys=True)), (
        "API contract drift: run `uv run benchserver export-openapi`")


def test_spa_fallback(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>st</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    ctx = make_ctx(make_settings(tmp_path, frontend_dist=dist))
    with client_for(ctx) as c:
        assert "<title>st</title>" in c.get("/runs/abc").text
        assert c.get("/assets/app.js").headers["cache-control"].startswith("public")
        assert c.get("/api/unknown").status_code == 404
        assert c.get("/../../etc/passwd").status_code in (200, 404)  # never escapes dist
        assert "root:" not in c.get("/../../etc/passwd").text


def test_openapi_file_is_committed():
    assert Path(ROOT / "contracts" / "openapi.json").exists()
