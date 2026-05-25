# Plan 10 — Testing & Benchmarks

> Covers: Doc 15 (Testing Strategy — full), Doc 14 §7 (Testing Laws), Doc 02 §5 (Acceptance Criteria)

---

## 1. TEST ARCHITECTURE

```
tests/
├── conftest.py                    # Shared fixtures, factories, test DB setup
├── unit/
│   ├── extraction/
│   │   ├── test_rule_based.py     # Rule-based extractor tests
│   │   ├── test_ner_extractor.py  # spaCy NER tests
│   │   ├── test_llm_extractor.py  # LLM extraction (mocked)
│   │   ├── test_sensitive_filter.py # Sensitive data patterns
│   │   ├── test_confidence_scorer.py
│   │   └── test_hypothetical.py   # Hypothetical/negation filtering
│   ├── conflict/
│   │   ├── test_detection.py      # Conflict candidate detection
│   │   ├── test_temporal.py       # Temporal resolution strategy
│   │   ├── test_preference.py     # Preference merge strategy
│   │   └── test_resolution.py     # Full resolution flow
│   ├── decay/
│   │   ├── test_retention.py      # Retention score computation
│   │   ├── test_decay_cycle.py    # Decay worker logic
│   │   └── test_permanent.py      # Permanent nodes never decay
│   ├── retrieval/
│   │   ├── test_intent.py         # Intent analysis
│   │   ├── test_ranking.py        # Context ranking
│   │   ├── test_budget.py         # Token budget enforcement
│   │   └── test_context_build.py  # Context string construction
│   ├── api/
│   │   ├── test_capture.py        # Capture endpoint
│   │   ├── test_context.py        # Context endpoint
│   │   ├── test_workspace.py      # Workspace CRUD
│   │   ├── test_nodes.py          # Node CRUD + boost
│   │   ├── test_auth.py           # Bearer token validation
│   │   └── test_health.py         # Health endpoint
│   └── services/
│       ├── test_workspace_service.py
│       ├── test_embedding_service.py
│       └── test_onboarding_service.py
├── integration/
│   ├── test_capture_pipeline.py   # Full capture → extract → commit
│   ├── test_context_retrieval.py  # Full retrieval → rank → build
│   ├── test_conflict_flow.py      # Extract → detect → resolve
│   ├── test_decay_flow.py         # Decay cycle end-to-end
│   └── test_workspace_lifecycle.py
├── benchmarks/
│   ├── samples/
│   │   ├── developer/             # 100 dev conversation pairs
│   │   ├── researcher/            # 100 researcher pairs
│   │   ├── product/               # 100 PM pairs
│   │   ├── creative/              # 100 creative pairs
│   │   └── edge_cases/            # 100 edge cases
│   ├── labels/
│   │   ├── developer.json
│   │   ├── researcher.json
│   │   ├── product.json
│   │   ├── creative.json
│   │   └── edge_cases.json
│   ├── run_benchmarks.py          # Benchmark runner
│   ├── targets.json               # Quality targets
│   └── test_quality_targets.py    # CI-runnable quality gate
├── performance/
│   └── test_latency.py            # All latency benchmarks
└── e2e/
    └── test_capture_flow.py       # Playwright browser tests
```

---

## 2. SHARED FIXTURES (tests/conftest.py)

```python
import pytest
from pathlib import Path

@pytest.fixture
def tmp_workspace(tmp_path):
    """Creates a test workspace with empty DB."""
    ws = create_test_workspace(tmp_path, name="Test Workspace")
    yield ws
    # Cleanup handled by tmp_path

@pytest.fixture
def workspace_with_data(tmp_path):
    """Workspace with 50 pre-populated nodes."""
    ws = create_test_workspace(tmp_path)
    seed_test_nodes(ws, distribution={
        NodeType.GOAL: 5, NodeType.DECISION: 10,
        NodeType.TECHNICAL_FACT: 15, NodeType.ENTITY: 10,
        NodeType.TASK: 5, NodeType.PROBLEM: 5,
        NodeType.EVENT: 3,                                 # Doc 04 §4
    })
    return ws

@pytest.fixture
def workspace_with_1000_nodes(tmp_path):
    """Large workspace for performance tests."""
    ws = create_test_workspace(tmp_path)
    seed_test_nodes(ws, node_count=1000)
    return ws

@pytest.fixture
def two_workspaces(tmp_path):
    """Two isolated workspaces for contamination tests."""
    ws_a = create_test_workspace(tmp_path / "a", name="Workspace A")
    ws_b = create_test_workspace(tmp_path / "b", name="Workspace B")
    seed_test_nodes(ws_a, node_count=30)
    seed_test_nodes(ws_b, node_count=30)
    return ws_a, ws_b

@pytest.fixture
def node_factory():
    """Factory with sensible defaults."""
    def _factory(**kwargs):
        defaults = {
            "id": generate_id(), "workspace_id": "ws_test",
            "node_type": NodeType.DECISION, "tier": MemoryTier.EPISODIC,
            "content": "Test content", "structured_data": {},
            "importance_score": 0.7, "extraction_confidence": 0.85,
            "user_verified": False, "status": NodeStatus.ACTIVE,
            "decay_rate": 0.05, "is_permanent": False,
            "reinforcement_count": 0, "version": 1,
            "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
        }
        defaults.update(kwargs)
        return MemoryNode(**defaults)
    return _factory

@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}

@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)

@pytest.fixture
async def two_populated_workspaces(db_manager, node_factory):
    """Two workspaces each with ~100 nodes for workspace switch benchmarks."""
    ws_a = await workspace_service.create(name="Benchmark WS A")
    ws_b = await workspace_service.create(name="Benchmark WS B")
    for _ in range(100):
        await node_factory.create(workspace_id=ws_a.id)
        await node_factory.create(workspace_id=ws_b.id)
    return ws_a.id, ws_b.id

@pytest.fixture
def running_engine_process():
    """Start the engine as a subprocess, wait for /health, yield psutil.Process."""
    import subprocess, time, httpx, psutil

    proc = subprocess.Popen(
        ["mnemosyne-engine", "--port", "7433", "--test-mode"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    # Wait for engine to be healthy (max 10 seconds)
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            r = httpx.get("http://localhost:7433/health", timeout=1)
            if r.json().get("status") == "healthy":
                break
        except Exception:
            time.sleep(0.2)

    yield psutil.Process(proc.pid)

    proc.terminate()
    proc.wait(timeout=5)
```

---

## 3. KEY UNIT TESTS

### 3.1 Extraction Tests (Doc 15 §2.1)
```python
# tests/unit/extraction/test_rule_based.py
class TestRuleBasedExtraction:
    def test_detects_technology_stack(self, extractor):
        results = extractor.extract("We're using FastAPI and PostgreSQL.")
        values = [r.structured_data['value'] for r in results]
        assert "FastAPI" in values and "PostgreSQL" in values

    def test_detects_explicit_decision(self, extractor):
        results = extractor.extract("We decided to remove offline mode from the MVP.")
        decisions = [r for r in results if r.node_type == NodeType.DECISION]
        assert len(decisions) >= 1

    def test_does_not_extract_hypothetical(self, extractor):
        results = extractor.extract("What if we used MongoDB instead?")
        facts = [r for r in results if r.node_type == NodeType.TECHNICAL_FACT]
        assert not any("MongoDB" in r.content for r in facts)

    def test_does_not_extract_negated(self, extractor):
        results = extractor.extract("We won't be using Cassandra.")
        assert not any("Cassandra" in r.content and "won't" not in r.content
                       for r in results)

    def test_trivial_message_no_extractions(self, extractor):
        assert len(extractor.extract("Thanks, that was helpful!")) == 0

    def test_confidence_in_bounds(self, extractor):
        for r in extractor.extract("We use React for the frontend."):
            assert 0.0 <= r.confidence <= 1.0
```

### 3.2 Sensitive Data Filter (Doc 15 §2.1)
```python
# tests/unit/extraction/test_sensitive_filter.py
class TestSensitiveFilter:
    @pytest.mark.parametrize("text,label", [
        ("sk-abc123def456ghi789jkl012mno345pqr", "OpenAI API key"),
        ("AKIAIOSFODNN7EXAMPLE", "AWS Access Key"),
        ("-----BEGIN RSA PRIVATE KEY-----", "Private key"),
        ("123-45-6789", "SSN"),
        ("4532-1234-5678-9012", "Credit card"),
        ("postgresql://user:pass@localhost/db", "Database connection string"),
    ])
    def test_detects_sensitive(self, text, label):
        result = contains_sensitive_data(text)
        assert result.is_sensitive and result.pattern_matched == label

    def test_clean_text_passes(self):
        assert not contains_sensitive_data("Implement retry with exponential backoff.").is_sensitive

    def test_api_key_in_longer_text(self):
        assert contains_sensitive_data("Key: sk-abc123def456ghi789jkl012mno345pqr ok").is_sensitive
```

### 3.3 Conflict Resolution (Doc 15 §2.2)
```python
# tests/unit/conflict/test_temporal.py
class TestTemporalResolution:
    def test_newer_wins(self, node_factory):
        older = node_factory(content="DB: PostgreSQL", created_at=datetime(2025,6,1))
        newer = node_factory(content="DB: MongoDB", created_at=datetime(2025,6,15))
        result = resolve_temporal(ConflictCandidate(node_a=older, node_b=newer,
                                  conflict_type=ConflictType.DIRECT_FACT))
        assert result.resolved and result.winning_node.id == newer.id

    def test_user_verified_needs_review(self, node_factory):
        verified = node_factory(content="DB: PostgreSQL", user_verified=True)
        system = node_factory(content="DB: MongoDB", user_verified=False)
        result = resolve_temporal(ConflictCandidate(node_a=verified, node_b=system,
                                  conflict_type=ConflictType.DIRECT_FACT))
        assert not result.resolved and result.needs_review

# tests/unit/decay/test_retention.py
class TestDecay:
    def test_permanent_never_decays(self, node_factory):
        node = node_factory(is_permanent=True,
                           last_accessed=datetime.utcnow() - timedelta(days=365))
        assert compute_retention(node) == 1.0

    def test_old_unaccessed_decays(self, node_factory):
        node = node_factory(importance_score=0.5, decay_rate=0.05,
                           last_accessed=datetime.utcnow() - timedelta(days=90))
        assert compute_retention(node) < 0.4
```

### 3.4 API Tests (Doc 15 §2.3)
```python
# tests/unit/api/test_capture.py
class TestCaptureEndpoint:
    def test_valid_capture_202(self, client, auth_headers):
        r = client.post("/api/v1/capture", json=VALID_CAPTURE, headers=auth_headers)
        assert r.status_code == 202 and r.json()["status"] == "queued"

    def test_sensitive_blocked(self, client, auth_headers):
        payload = {**VALID_CAPTURE, "user_message": "sk-abc123def456ghi789jkl012mno345pqr"}
        r = client.post("/api/v1/capture", json=payload, headers=auth_headers)
        assert r.json()["status"] == "blocked"

    def test_no_auth_401(self, client):
        assert client.post("/api/v1/capture", json={}).status_code == 401

    def test_too_long_413(self, client, auth_headers):
        payload = {**VALID_CAPTURE, "user_message": "x" * 60000}
        assert client.post("/api/v1/capture", json=payload, headers=auth_headers).status_code == 413
```

---

## 4. INTEGRATION TESTS (Doc 15 §3)

```python
# tests/integration/test_capture_pipeline.py
class TestFullCapturePipeline:
    async def test_decision_extracted_and_committed(self, pipeline):
        result = await pipeline.process(make_capture(
            user="We decided to use SQLite for local storage.",
            ai="SQLite makes sense for local-first..."
        ))
        assert len(result.auto_committed) >= 1
        assert result.auto_committed[0].node_type == NodeType.DECISION
        assert pipeline.db.get_node(result.auto_committed[0].id) is not None

    async def test_low_confidence_goes_to_pending(self, pipeline):
        result = await pipeline.process(make_capture(
            user="Maybe we should think about adding auth...",
            ai="Authentication is something to consider..."
        ))
        assert len(result.pending_review) > 0

    async def test_conflict_on_contradiction(self, pipeline):
        await pipeline.process(make_capture(user="Our database is PostgreSQL", ai="Good choice."))
        await pipeline.process(make_capture(user="We switched to MongoDB", ai="More flexible."))
        assert len(pipeline.db.get_conflicts(status='PENDING')) >= 1

# tests/integration/test_context_retrieval.py
class TestContextRetrieval:
    async def test_goals_always_included(self, workspace_with_data):
        result = await RetrievalService(workspace_with_data).get_context(
            workspace_id=workspace_with_data.id, token_budget=2000)
        assert any("goal" in item.lower() for item in result.context_string.split('\n'))

    async def test_respects_token_budget(self, workspace_with_data):
        result = await RetrievalService(workspace_with_data).get_context(
            workspace_id=workspace_with_data.id, token_budget=500)
        assert result.token_count <= 500

    async def test_no_cross_workspace_contamination(self, two_workspaces):
        ws_a, ws_b = two_workspaces
        result = await RetrievalService().get_context(workspace_id=ws_a.id, token_budget=2000)
        assert all(n.workspace_id == ws_a.id for n in result.nodes_included)
```

---

## 5. MEMORY QUALITY BENCHMARKS (Doc 15 §4)

### Benchmark Dataset: 500 labeled conversation pairs across 5 personas.

### tests/benchmarks/targets.json
```json
{
  "overall_precision": 0.85,
  "overall_recall": 0.75,
  "false_positive_rate": 0.10,
  "by_type": {
    "decision":       { "precision": 0.82, "recall": 0.78 },
    "goal":           { "precision": 0.88, "recall": 0.74 },
    "technical_fact":  { "precision": 0.91, "recall": 0.81 },
    "entity":         { "precision": 0.93, "recall": 0.86 },
    "preference":     { "precision": 0.79, "recall": 0.68 }
  }
}
```

### tests/benchmarks/run_benchmarks.py
```python
class ExtractionBenchmark:
    def run(self, category: str = 'all') -> BenchmarkReport:
        samples = load_samples(category)
        labels = load_labels(category)
        results = [evaluate_extraction(run_extraction_pipeline(s), l)
                   for s, l in zip(samples, labels)]
        return BenchmarkReport(
            total_samples=len(results),
            precision=self._precision(results),
            recall=self._recall(results),
            false_positive_rate=self._fpr(results),
            by_node_type=self._by_type(results),
            failed_samples=[r for r in results if not r.passed]
        )

# tests/benchmarks/test_quality_targets.py — CI gate
def test_extraction_meets_targets():
    report = ExtractionBenchmark().run()
    targets = json.load(open("tests/benchmarks/targets.json"))
    assert report.precision >= targets["overall_precision"]
    assert report.recall >= targets["overall_recall"]
    assert report.false_positive_rate <= targets["false_positive_rate"]
```

---

## 6. PERFORMANCE TESTS (Doc 15 §6, Doc 14 §6)

```python
# tests/performance/test_latency.py
class TestLatencyTargets:
    async def test_retrieval_under_300ms(self, workspace_with_100_nodes, benchmark):
        result = await benchmark.async_run(service.get_context,
            workspace_id=workspace_with_100_nodes.id, token_budget=2000)
        assert benchmark.stats['mean'] < 0.300

    def test_sensitive_filter_under_10ms(self, benchmark):
        benchmark.run(contains_sensitive_data, "We decided to use FastAPI " * 100)
        assert benchmark.stats['mean'] < 0.010

    async def test_extraction_under_500ms(self, benchmark):
        result = await benchmark.async_run(process_capture, create_test_capture(2000))
        assert benchmark.stats['mean'] < 0.500

    def test_graph_5hop_under_50ms(self, workspace_with_1000_nodes, benchmark):
        node = workspace_with_1000_nodes.get_random_node()
        benchmark.run(graph_traverse, center_node_id=node.id, max_hops=5)
        assert benchmark.stats['mean'] < 0.050

    def test_fts_under_100ms(self, workspace_with_1000_nodes, benchmark):
        benchmark.run(full_text_search, workspace_with_1000_nodes.id, "database")
        assert benchmark.stats['mean'] < 0.100
    
    async def test_workspace_switch_under_100ms(
        self,
        two_populated_workspaces,   # fixture: two workspaces each with ~100 nodes
        workspace_service,
        benchmark
    ):
        """Doc 14 §6: workspace switch < 100ms hard limit."""
        ws_a_id, ws_b_id = two_populated_workspaces

        async def switch():
            # Simulate: set active workspace, load its context
            await workspace_service.set_active(ws_b_id)
            await workspace_service.set_active(ws_a_id)

        await benchmark.async_run(switch)
        assert benchmark.stats['mean'] < 0.100, (
            f"Workspace switch too slow: {benchmark.stats['mean']*1000:.1f}ms (limit: 100ms)"
        )

    async def test_sidebar_load_under_300ms(
        self,
        workspace_with_100_nodes,
        retrieval_service,
        benchmark
    ):
        """Doc 14 §6: sidebar load < 300ms. Simulates the data fetch the sidebar
        triggers on open: active workspace nodes + pending count + recent sessions."""
        from backend.services.workspace_service import WorkspaceService

        async def sidebar_load():
            ws_id = workspace_with_100_nodes.id
            # These are the three parallel fetches the sidebar triggers on mount
            import asyncio
            await asyncio.gather(
                retrieval_service.get_context(workspace_id=ws_id, token_budget=500),
                workspace_service.get_pending_count(ws_id),
                workspace_service.get_recent_sessions(ws_id, limit=5),
            )

        await benchmark.async_run(sidebar_load)
        assert benchmark.stats['mean'] < 0.300, (
            f"Sidebar load too slow: {benchmark.stats['mean']*1000:.1f}ms (limit: 300ms)"
        )

def test_engine_ram_at_rest_under_300mb(self, running_engine_process):
        """Doc 14 §6 hard limit: engine RAM < 300MB at rest.

        `running_engine_process` fixture: starts the engine subprocess, waits for
        /health to return healthy, then yields the psutil.Process object.
        """
        import psutil

        proc = running_engine_process          # psutil.Process
        rss_bytes = proc.memory_info().rss
        rss_mb = rss_bytes / (1024 * 1024)

        assert rss_mb < 300, (
            f"Engine RAM at rest too high: {rss_mb:.1f} MB (hard limit: 300 MB). "
            f"Target is <150 MB."
        )

        # Also warn (not fail) if above target
        if rss_mb > 150:
            import warnings
            warnings.warn(
                f"Engine RAM ({rss_mb:.1f} MB) exceeds 150 MB target. "
                f"Still within 300 MB hard limit but investigate before release.",
                stacklevel=2
            )

    def test_engine_ram_target_under_150mb(self, running_engine_process):
        """Doc 14 §6 soft target: engine RAM < 150MB at rest.
        Marked xfail if it fails — this is a target, not a hard limit.
        """
        import psutil, pytest

        proc = running_engine_process
        rss_mb = proc.memory_info().rss / (1024 * 1024)

        if rss_mb >= 150:
            pytest.xfail(
                f"RAM target missed: {rss_mb:.1f} MB ≥ 150 MB. "
                f"Not a release blocker (hard limit is 300 MB) but must be tracked."
            )
```

---

## 7. E2E TESTS (Doc 15 §5)

```python
# tests/e2e/test_capture_flow.py — Playwright
class TestCaptureE2E:
    async def test_capture_on_claude(self, browser_with_extension, test_engine):
        page = await browser_with_extension.new_page()
        await page.goto("https://claude.ai/chat")
        await page.fill('[data-testid="chat-input"]', "We decided to use FastAPI")
        await page.click('[data-testid="send-button"]')
        await page.wait_for_selector('[data-testid="ai-response"]')
        await asyncio.sleep(2)
        nodes = test_engine.get_nodes(workspace_id="ws_test")
        assert any("FastAPI" in n.content for n in nodes)

    async def test_injection_indicator_visible(self, browser_with_extension, test_engine):
        test_engine.create_test_nodes("ws_test")
        page = await browser_with_extension.new_page()
        await page.goto("https://claude.ai/chat")
        indicator = await page.wait_for_selector('[data-testid="mnemosyne-injection-indicator"]')
        assert "Mnemosyne" in await indicator.inner_text()

    async def test_sensitive_not_stored(self, browser_with_extension, test_engine):
        initial = len(test_engine.get_nodes("ws_test"))
        page = await browser_with_extension.new_page()
        await page.goto("https://claude.ai/chat")
        await page.fill('[data-testid="chat-input"]', "Key: sk-abc123def456ghi789jkl012mno345pqr")
        await page.click('[data-testid="send-button"]')
        await asyncio.sleep(2)
        assert len(test_engine.get_nodes("ws_test")) == initial
```

---

## 8. TYPESCRIPT EXTENSION TESTS (Doc 15 §2.4)

```typescript
// tests/unit/sensitiveFilter.test.ts — Vitest
describe('SensitiveDataFilter', () => {
  test('detects API keys', () => expect(containsSensitiveData('sk-abc123...')).toBe(true))
  test('passes clean text', () => expect(containsSensitiveData('Use FastAPI')).toBe(false))
  test('detects credit cards', () => expect(containsSensitiveData('4532 1234 5678 9012')).toBe(true))
})

describe('WorkspaceDetector', () => {
  test('selects highest above threshold', async () => {
    const result = await selectWorkspace([{id:'ws1',score:0.82},{id:'ws2',score:0.45}], 0.55)
    expect(result.workspaceId).toBe('ws1')
  })
  test('suggests new when all below', async () => {
    const result = await selectWorkspace([{id:'ws1',score:0.42}], 0.55)
    expect(result.action).toBe('SUGGEST_NEW_WORKSPACE')
  })
})
```

---

## 9. CI PIPELINE (Doc 15 §7)

```yaml
# .github/workflows/ci.yml
jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: ruff check backend/
      - run: mypy backend/ --strict
      - run: pnpm eslint extension/
      - run: pnpm tsc --noEmit

  unit-tests:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    steps:
      - run: uv run pytest tests/unit/ -v --cov=backend --cov-report=xml
      - run: pnpm vitest run

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - run: uv run pytest tests/integration/ -v

  quality-benchmarks:
    runs-on: ubuntu-latest
    steps:
      - run: uv run python tests/benchmarks/run_benchmarks.py
      - run: uv run pytest tests/benchmarks/test_quality_targets.py -v

  performance-tests:
    runs-on: ubuntu-latest
    steps:
      - run: uv run pytest tests/performance/ --benchmark-only

  e2e-tests:  # Nightly only
    if: github.event_name == 'schedule'
    runs-on: ubuntu-latest
    steps:
      - run: pnpm build:extension:test
      - run: uv run pytest tests/e2e/ -v
```

**PR Gates:** All unit + integration + quality benchmarks must pass. Performance must not regress >20%.

---

## Files Summary

| File | Purpose |
|------|---------|
| `tests/conftest.py` | Shared fixtures, factories |
| `tests/unit/extraction/test_rule_based.py` | Rule extraction tests |
| `tests/unit/extraction/test_ner_extractor.py` | NER tests |
| `tests/unit/extraction/test_llm_extractor.py` | LLM extraction tests |
| `tests/unit/extraction/test_sensitive_filter.py` | Sensitive pattern tests |
| `tests/unit/extraction/test_confidence_scorer.py` | Scoring tests |
| `tests/unit/extraction/test_hypothetical.py` | Hypothetical detection |
| `tests/unit/conflict/test_detection.py` | Conflict detection |
| `tests/unit/conflict/test_temporal.py` | Temporal resolution |
| `tests/unit/conflict/test_resolution.py` | Full resolution |
| `tests/unit/decay/test_retention.py` | Retention scoring |
| `tests/unit/decay/test_decay_cycle.py` | Decay cycle |
| `tests/unit/retrieval/test_ranking.py` | Context ranking |
| `tests/unit/retrieval/test_budget.py` | Token budget |
| `tests/unit/api/test_capture.py` | Capture API |
| `tests/unit/api/test_auth.py` | Auth tests |
| `tests/integration/test_capture_pipeline.py` | Full pipeline |
| `tests/integration/test_context_retrieval.py` | Full retrieval |
| `tests/integration/test_conflict_flow.py` | Conflict flow |
| `tests/benchmarks/run_benchmarks.py` | Benchmark runner |
| `tests/benchmarks/targets.json` | Quality targets |
| `tests/benchmarks/test_quality_targets.py` | CI quality gate |
| `tests/performance/test_latency.py` | Latency benchmarks |
| `tests/e2e/test_capture_flow.py` | Playwright E2E |
| `.github/workflows/ci.yml` | CI pipeline |

**Total: ~25 files.**

---

> **Next: Plan 11 — Deployment, CI/CD & Installers**
