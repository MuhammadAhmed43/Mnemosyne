"""API tests via FastAPI TestClient (runs the real lifespan + workers)."""

from __future__ import annotations

import os
from datetime import timezone

import pytest

from backend.utils.time import now_utc


@pytest.fixture
def client(tmp_path):
    # MNEMOSYNE_DATA_DIR isolates each test on every OS; APPDATA alone only works
    # on Windows, which let cross-test state leak (and break) on Linux CI.
    os.environ["MNEMOSYNE_DATA_DIR"] = str(tmp_path / "data")
    os.environ["APPDATA"] = str(tmp_path / "appdata")
    from fastapi.testclient import TestClient

    from backend.main import app

    with TestClient(app) as c:
        yield c


def _ts():
    return now_utc().replace(tzinfo=timezone.utc).isoformat()


def test_health_unauthenticated(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "healthy"


def test_pair_returns_token(client):
    r = client.get("/pair")
    assert r.status_code == 200 and r.json()["token"]


def test_workspaces_require_auth(client):
    assert client.get("/api/v1/workspaces").status_code == 401


def test_create_workspace_and_capture(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    ws = client.post("/api/v1/workspaces", json={"name": "API WS", "description": "test"}, headers=h)
    assert ws.status_code == 201
    wid = ws.json()["id"]

    blocked = client.post("/api/v1/capture", json={
        "session_id": "s", "platform": "claude",
        "user_message": "key sk-abc123def456ghi789jkl012mno345pqr", "ai_response": "ok",
        "timestamp": _ts(), "tab_url": "", "workspace_id": wid,
    }, headers=h)
    assert blocked.json()["status"] == "blocked"

    queued = client.post("/api/v1/capture", json={
        "session_id": "s", "platform": "claude",
        "user_message": "We decided to use FastAPI for the backend", "ai_response": "Good.",
        "timestamp": _ts(), "tab_url": "", "workspace_id": wid,
    }, headers=h)
    assert queued.status_code == 202 and queued.json()["status"] == "queued"


def test_save_note_resolves_workspace(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    wid = client.post("/api/v1/workspaces", json={"name": "Notes WS"}, headers=h).json()["id"]

    # No workspace_id given -> should resolve to the most-recently-active one.
    r = client.post("/api/v1/notes", json={
        "text": "Remember: the API key rotates every 90 days.",
        "platform": "chatgpt", "tab_url": "https://chatgpt.com/c/abc",
    }, headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is True and body["workspace_id"] == wid

    # The note is now a verified node in that workspace.
    nodes = client.get(f"/api/v1/workspaces/{wid}/nodes?search=rotates", headers=h).json()
    assert any("rotate" in n["content"].lower() for n in nodes["nodes"])


def test_empty_note_rejected(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/workspaces", json={"name": "WS"}, headers=h)
    assert client.post("/api/v1/notes", json={"text": "   "}, headers=h).status_code >= 400


def test_url_mapping_routes_context(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    a = client.post("/api/v1/workspaces", json={"name": "Alpha"}, headers=h).json()["id"]
    b = client.post("/api/v1/workspaces", json={"name": "Beta"}, headers=h).json()["id"]

    # Map a custom-GPT URL to Alpha (not the most-recently-created, which is Beta).
    m = client.post("/api/v1/mappings", json={
        "platform": "chatgpt", "workspace_id": a, "tab_url": "https://chatgpt.com/g/g-alpha-bot/c/xyz",
    }, headers=h)
    assert m.status_code == 200 and m.json()["url_pattern"] == "chatgpt.com/g/g-alpha-bot"

    # A context request on any chat under that GPT must resolve to Alpha via the
    # mapping, overriding the most-recently-active fallback (Beta).
    ctx = client.get(
        "/api/v1/context?platform=chatgpt&tab_url=https://chatgpt.com/g/g-alpha-bot/c/different",
        headers=h,
    ).json()
    assert ctx["workspace_id"] == a


def test_intent_classification_goal_vs_decision():
    from backend.extraction.rule_based import RuleBasedExtractor
    from backend.models.enums import NodeType
    ext = RuleBasedExtractor()

    # Aspirational first-person intent -> GOAL (auto-commit eligible)
    for msg in ("i want to work on kubernetes", "I'd like to use Go for the backend", "I plan to learn Rust"):
        goals = [c for c in ext.extract(msg, "") if c.node_type == NodeType.GOAL]
        assert goals and max(c.confidence for c in goals) >= 0.80, f"should be a Goal: {msg!r}"

    # Firm commitment -> DECISION (auto-commit eligible)
    for msg in ("Let's work with Kubernetes for this", "We'll use PostgreSQL", "I'm going to build a CLI tool"):
        decisions = [c for c in ext.extract(msg, "") if c.node_type == NodeType.DECISION]
        assert decisions and max(c.confidence for c in decisions) >= 0.80, f"should be a Decision: {msg!r}"


def test_commit_dedup_collapses_repeats(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    wid = client.post("/api/v1/workspaces", json={"name": "DedupWS"}, headers=h).json()["id"]
    # Same fact committed three times (as it would be across turns) -> one node.
    for _ in range(3):
        client.post(f"/api/v1/workspaces/{wid}/nodes/manual",
                    json={"node_type": "technical_fact", "content": "Uses Go"}, headers=h)
    counts = client.get(f"/api/v1/workspaces/{wid}/node-counts", headers=h).json()["counts"]
    assert counts.get("technical_fact", 0) == 1


def test_semantic_dedup_collapses_rephrasings(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    wid = client.post("/api/v1/workspaces", json={"name": "SemWS"}, headers=h).json()["id"]

    a = client.post(f"/api/v1/workspaces/{wid}/nodes/manual",
                    json={"node_type": "decision", "content": "We will use PostgreSQL as the primary database for storage."},
                    headers=h).json()

    # Stub the vector search so the next, differently-worded decision is judged
    # a near-duplicate of A (deterministic, independent of the embedding model).
    cont = client.app.state.container
    cont.embedding._available = True
    cont.embedding.search = lambda *a_, **k_: [(a["id"], 0.95)]

    client.post(f"/api/v1/workspaces/{wid}/nodes/manual",
                json={"node_type": "decision", "content": "Decided to go with PostgreSQL for the database layer here."},
                headers=h)

    counts = client.get(f"/api/v1/workspaces/{wid}/node-counts", headers=h).json()["counts"]
    assert counts.get("decision", 0) == 1  # rephrasing merged into the original


def test_reject_all_pending(client):
    from datetime import timedelta, timezone

    from backend.models.extraction import PendingReview

    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    wid = client.post("/api/v1/workspaces", json={"name": "PendWS"}, headers=h).json()["id"]

    repo = client.app.state.container.pending_repo(wid)
    exp = now_utc().replace(tzinfo=timezone.utc) + timedelta(days=7)
    for i in range(3):
        repo.create(PendingReview(
            workspace_id=wid, candidate_type="entity", candidate_content=f"junk{i}",
            candidate_confidence=0.7, expires_at=exp,
        ))
    assert client.get(f"/api/v1/workspaces/{wid}/pending", headers=h).json()["total"] == 3

    r = client.post(f"/api/v1/workspaces/{wid}/pending/reject-all", json={}, headers=h)
    assert r.status_code == 200 and r.json()["rejected"] == 3
    assert client.get(f"/api/v1/workspaces/{wid}/pending", headers=h).json()["total"] == 0


def test_ner_drops_lowercase_noise_entities():
    from backend.extraction.ner_extractor import _useful_entity
    # mislabeled common nouns -> dropped
    for junk in ("jargon", "metadata", "briefs", "decay", "pick", "ai"):
        assert _useful_entity(junk) is False
    # genuine names -> kept
    for ok in ("QuillBot", "Copy.ai", "API Gateway", "NATS", "Grammarly"):
        assert _useful_entity(ok) is True


def test_idea_intent_covers_info_seeking():
    from backend.extraction.idea_extractor import has_idea_intent
    assert has_idea_intent("is there an app which makes meeting scripts")
    assert has_idea_intent("i want a repo i can add to my cv")
    assert has_idea_intent("which tool is best for ghostwriting")
    assert has_idea_intent("recommend a backend framework")
    assert not has_idea_intent("ok thanks")


def test_idea_extractor_captures_insight():
    from backend.extraction.idea_extractor import IdeaExtractor
    from backend.models.enums import NodeType

    ext = IdeaExtractor()
    user = "Tell me more about the meal-prep subscription idea — how would it work?"
    ai = (
        "A meal-prep subscription delivers pre-portioned ingredients weekly. "
        "Customers pick recipes online, you source ingredients in bulk, and a "
        "fulfillment partner packs and ships chilled boxes. Revenue comes from a "
        "recurring weekly fee with tiered plans."
    )
    cands = ext.extract(user, ai)
    assert len(cands) == 1
    c = cands[0]
    assert c.node_type == NodeType.INSIGHT
    assert c.confidence >= 0.80  # auto-commit eligible
    assert "meal-prep subscription" in c.content.lower()
    assert c.structured_data["kind"] == "idea"

    # No elaboration intent -> nothing.
    assert ext.extract("thanks, that's helpful", ai) == []
    # Intent but a one-line answer -> not worth remembering.
    assert ext.extract(user, "Sure!") == []


def test_idea_auto_commits_via_pipeline():
    import asyncio
    from datetime import timezone

    from backend.config import MnemosyneConfig
    from backend.extraction.pipeline import ExtractionPipeline
    from backend.models.capture import CaptureRecord
    from backend.models.enums import NodeType, Platform

    pipe = ExtractionPipeline(MnemosyneConfig())
    pipe.llm._available = False  # prove the rule-based idea path works without Ollama
    rec = CaptureRecord(
        session_id="s", platform=Platform.CHATGPT, workspace_id="w",
        user_message="Explain how a habit-tracker app would work and how I'd build it.",
        ai_response=(
            "A habit-tracker lets users define daily habits and check them off. "
            "You store habits and completion logs, render a streak calendar, and "
            "send reminder notifications. Build it with a local-first store so it "
            "works offline and syncs when online."
        ),
        timestamp=now_utc().replace(tzinfo=timezone.utc),
    )
    result = asyncio.run(pipe.run(rec))
    insights = [c for c in result.to_commit if c.node_type == NodeType.INSIGHT]
    assert insights, "idea turn should auto-commit an INSIGHT"


def test_encryption_migrates_plaintext_and_hides_data():
    import sqlite3
    import pytest

    from backend.db.encryption import SQLCIPHER_AVAILABLE, _is_plaintext_sqlite, open_connection

    if not SQLCIPHER_AVAILABLE:
        pytest.skip("SQLCipher driver not installed in this environment")

    import tempfile
    from pathlib import Path

    p = Path(tempfile.mkdtemp()) / "graph.db"
    # Existing PLAINTEXT db with a recognizable secret.
    c = sqlite3.connect(str(p))
    c.execute("CREATE TABLE m(x)")
    c.execute("INSERT INTO m VALUES('top_secret_memory')")
    c.commit()
    c.close()
    assert _is_plaintext_sqlite(p)

    key = "a" * 64
    conn, encrypted = open_connection(p, key)
    assert encrypted is True
    assert conn.execute("SELECT x FROM m").fetchone()[0] == "top_secret_memory"  # data preserved
    conn.close()

    # On disk it's now encrypted: no SQLite header, no plaintext leak, stdlib can't read.
    assert not _is_plaintext_sqlite(p)
    assert b"top_secret_memory" not in p.read_bytes()
    with pytest.raises(sqlite3.DatabaseError):
        sqlite3.connect(str(p)).execute("SELECT * FROM m").fetchall()


def test_health_reports_encryption(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    body = client.get("/health").json()
    assert "encryption_at_rest" in body  # surfaced honestly either way


def test_llm_extraction_toggle_gates_the_pass():
    import asyncio
    from datetime import timezone

    from backend.config import MnemosyneConfig
    from backend.extraction.pipeline import ExtractionPipeline
    from backend.models.capture import CaptureRecord
    from backend.models.enums import Platform

    pipe = ExtractionPipeline(MnemosyneConfig())
    calls = {"n": 0}

    async def fake_extract(*_a, **_k):
        calls["n"] += 1
        return []

    pipe.llm.extract = fake_extract  # type: ignore[assignment]
    rec = CaptureRecord(
        session_id="s", platform=Platform.CHATGPT, workspace_id="w",
        user_message="Explain how a habit-tracker app would work and how I'd build it.",
        ai_response=(
            "A habit-tracker lets users define daily habits and check them off each day. "
            "You store the habits and a completion log, then render a streak calendar so "
            "progress is visible. Reminder notifications nudge people to keep going. "
            "Build it local-first so it works offline and syncs when a connection returns, "
            "and add weekly summaries to reinforce the streaks."
        ),
        timestamp=now_utc().replace(tzinfo=timezone.utc),
    )
    # Disabled -> the LLM pass must not run, even on an idea turn that would force it.
    asyncio.run(pipe.run(rec, llm_enabled=False))
    assert calls["n"] == 0
    # Enabled -> idea intent forces the LLM pass.
    asyncio.run(pipe.run(rec, llm_enabled=True))
    assert calls["n"] == 1


def test_context_renders_insight_and_note_sections():
    from backend.models.context import ContextNode
    from backend.models.enums import NodeType
    from backend.services.retrieval_service import RetrievalService

    svc = RetrievalService.__new__(RetrievalService)  # _build needs no deps
    nodes = [
        ContextNode(node_id="1", node_type=NodeType.INSIGHT, content="Idea — habit tracker: streak calendar app", relevance_score=1.0, source="insight"),
        ContextNode(node_id="2", node_type=NodeType.USER_NOTE, content="API key rotates every 90 days", relevance_score=1.0, source="user_note"),
    ]
    body = svc._build("WS", nodes, "claude")
    assert "Ideas & Insights" in body and "habit tracker" in body
    assert "Saved Notes" in body and "rotates every 90 days" in body


def test_move_node_between_workspaces(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    a = client.post("/api/v1/workspaces", json={"name": "Source"}, headers=h).json()["id"]
    b = client.post("/api/v1/workspaces", json={"name": "Target"}, headers=h).json()["id"]
    nid = client.post(f"/api/v1/workspaces/{a}/nodes/manual",
                      json={"node_type": "decision", "content": "Use PostgreSQL"}, headers=h).json()["id"]

    r = client.post(f"/api/v1/workspaces/{a}/nodes/{nid}/move",
                    json={"target_workspace_id": b}, headers=h)
    assert r.status_code == 200 and r.json()["moved"] is True

    assert client.get(f"/api/v1/workspaces/{a}/node-counts", headers=h).json()["total"] == 0
    assert client.get(f"/api/v1/workspaces/{b}/node-counts", headers=h).json()["counts"].get("decision", 0) == 1


def test_ws_events_rejects_bad_token(client):
    import pytest
    with pytest.raises(Exception):  # handshake closed with policy-violation
        with client.websocket_connect("/ws/events?token=not-the-token") as ws:
            ws.receive_json()


def test_ws_events_accepts_valid_token(client):
    token = client.get("/pair").json()["token"]
    # A valid token completes the handshake; the connection registers a subscriber.
    with client.websocket_connect(f"/ws/events?token={token}"):
        assert len(client.app.state.container.subscribers) >= 1


def test_node_counts_endpoint(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    wid = client.post("/api/v1/workspaces", json={"name": "Counts WS"}, headers=h).json()["id"]

    # Seed a couple of manual nodes of different types.
    client.post(f"/api/v1/workspaces/{wid}/nodes/manual", json={"node_type": "decision", "content": "Use Postgres"}, headers=h)
    client.post(f"/api/v1/workspaces/{wid}/nodes/manual", json={"node_type": "insight", "content": "Idea — caching layer: use Redis read-through"}, headers=h)
    client.post(f"/api/v1/workspaces/{wid}/nodes/manual", json={"node_type": "insight", "content": "Idea — queue: use a disk-backed journal"}, headers=h)

    r = client.get(f"/api/v1/workspaces/{wid}/node-counts", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["insight"] == 2
    assert body["counts"]["decision"] == 1
    assert body["total"] == 3

    # `node-counts` must not be swallowed by the /nodes/{node_id} route.
    assert "counts" in body


def test_suggest_name_from_message(client):
    svc = client.app.state.container.workspace_service
    name = svc.suggest_name("How do I file my taxes for 2026?", "")
    assert "File" in name and "Taxes" in name and "2026" in name
    assert len(name) <= 40
    assert svc.suggest_name("", "") == "New Topic"


def test_offtopic_capture_auto_creates_named_workspace(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    client.post("/api/v1/workspaces", json={"name": "Alpha", "description": "fastapi backend"}, headers=h)

    # Force a confident topic mismatch so the auto-create branch fires
    # deterministically (independent of the embedding model's exact scores).
    cont = client.app.state.container
    cont.embedding._available = True
    cont.workspace_service.infer_workspace = lambda *a, **k: ("", 0.1)

    r = client.post("/api/v1/capture", json={
        "session_id": "s2", "platform": "chatgpt",
        "user_message": "How do I file my self-employment taxes and quarterly estimated payments for 2026?",
        "ai_response": "You report self-employment income on Schedule C and pay quarterly estimates.",
        "timestamp": _ts(), "tab_url": "https://chatgpt.com/c/tax-chat",
    }, headers=h)
    body = r.json()
    assert r.status_code == 202 and body["status"] == "queued"
    assert body["workspace_created"] is True
    assert body["workspace_name"]  # named from the conversation content
    assert client.get("/api/v1/workspaces", headers=h).json()["total"] == 2


def test_settings_thresholds_drive_routing():
    """Lowering auto_commit_threshold should push a candidate that would normally
    sit in pending review straight to auto-commit (the scorer used to ignore the
    setting). Tested directly against the scorer, which the pipeline now feeds."""
    from backend.extraction.confidence_scorer import ConfidenceScorer
    from backend.models.extraction import ExtractionCandidate
    from backend.models.enums import NodeType

    scorer = ConfidenceScorer()
    cand = ExtractionCandidate(
        node_type=NodeType.GOAL, content="ship the beta", confidence=0.72,
        source_pass="rule_based", evidence="we want to ship the beta",
    )
    # Default thresholds (0.80 / 0.60): 0.72 -> pending review.
    default = scorer.route_candidates([cand])
    assert len(default["pending_review"]) == 1 and not default["auto_commit"]

    # Lowered auto-commit threshold to 0.70: same candidate -> auto-commit.
    lowered = scorer.route_candidates([cand], auto_commit_threshold=0.70, min_confidence=0.50)
    assert len(lowered["auto_commit"]) == 1 and not lowered["pending_review"]


def test_settings_reject_out_of_range(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    s = client.get("/api/v1/settings", headers=h).json()
    s["auto_commit_threshold"] = 1.5  # invalid
    assert client.put("/api/v1/settings", json=s, headers=h).status_code == 422


def test_settings_round_trip(client):
    token = client.get("/pair").json()["token"]
    h = {"Authorization": f"Bearer {token}"}
    s = client.get("/api/v1/settings", headers=h).json()
    s["token_budget"] = 1500
    assert client.put("/api/v1/settings", json=s, headers=h).status_code == 200
    assert client.get("/api/v1/settings", headers=h).json()["token_budget"] == 1500
