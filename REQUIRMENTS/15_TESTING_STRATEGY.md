# DOCUMENT 15 — TESTING STRATEGY
## Unit, Integration, E2E, and Memory Quality Tests
**Project Mnemosyne**
**Version: 1.0.0**

---

## 1. TESTING PHILOSOPHY

Mnemosyne has two categories of failure that demand different testing strategies:

**Category A: Standard Software Failures**
- API endpoints return wrong status codes
- Database writes fail
- UI components don't render
- Auth token validation fails

These are caught by standard unit and integration tests.

**Category B: Cognitive Failures**
- Extraction produces false positives (stores things that aren't true)
- Conflict resolution picks the wrong winner
- Context injection includes irrelevant information
- Decay removes information the user still needs

These are the **uniquely dangerous** failures. A wrong API response is recoverable. A wrong memory corrupts the user's cognitive workspace silently. These require a dedicated quality testing layer.

**The testing pyramid for Mnemosyne:**
```
         ▲
        /E2E\         ← 20 tests — full platform simulation
       /──────\
      /Integration\   ← 150 tests — service + API layer
     /────────────\
    / Memory Quality\  ← 500 labeled samples — extraction + retrieval accuracy
   /────────────────\
  /    Unit Tests    \ ← 800+ tests — all functions, all edge cases
 /────────────────────\
```

---

## 2. UNIT TESTS

**Framework:** pytest 8.x (Python), Vitest 1.x (TypeScript)  
**Target coverage:** 90%+ on all service layer code

### 2.1 Extraction Pipeline Tests

```python
# tests/extraction/test_rule_based.py

class TestRuleBasedExtraction:
    
    def test_detects_technology_stack(self):
        extractor = RuleBasedExtractor()
        text = "We're using FastAPI for the backend and PostgreSQL as our database."
        results = extractor.extract(text)
        
        types = [r.structured_data['value'] for r in results]
        assert "FastAPI" in types
        assert "PostgreSQL" in types
    
    def test_detects_explicit_decision(self):
        text = "We decided to remove offline mode from the MVP because of scope."
        results = extractor.extract(text)
        
        decisions = [r for r in results if r.node_type == NodeType.DECISION]
        assert len(decisions) >= 1
        assert "offline mode" in decisions[0].content.lower()
    
    def test_does_not_extract_hypothetical(self):
        text = "What if we used MongoDB instead of PostgreSQL? Let's think about that."
        results = extractor.extract(text)
        
        tech_facts = [r for r in results if r.node_type == NodeType.TECHNICAL_FACT]
        # MongoDB should NOT be extracted — it's hypothetical
        assert not any("MongoDB" in r.content for r in tech_facts)
    
    def test_does_not_extract_negated_decision(self):
        text = "We won't be using Cassandra — that was ruled out early."
        results = extractor.extract(text)
        
        decisions = [r for r in results if r.node_type == NodeType.DECISION]
        # "Cassandra" should not be a positive tech fact
        assert not any("Cassandra" in r.content and "won't" not in r.content 
                       for r in decisions)
    
    def test_confidence_scores_within_bounds(self):
        text = "We use React for the frontend."
        results = extractor.extract(text)
        
        for r in results:
            assert 0.0 <= r.confidence <= 1.0
    
    def test_trivial_message_produces_no_extractions(self):
        text = "Thanks, that was helpful!"
        results = extractor.extract(text)
        assert len(results) == 0


class TestSensitiveDataFilter:
    
    @pytest.mark.parametrize("sensitive_text,pattern_label", [
        ("sk-abc123def456ghi789jkl012mno345pqr", "OpenAI API key"),
        ("AKIAIOSFODNN7EXAMPLE", "AWS Access Key"),
        ("my password is hunter2", "Generic credential"),
        ("-----BEGIN RSA PRIVATE KEY-----", "Private key"),
        ("123-45-6789", "SSN"),
        ("4532-1234-5678-9012", "Credit card"),
        ("postgresql://user:password123@localhost:5432/db", "Database connection string"),
    ])
    def test_detects_sensitive_patterns(self, sensitive_text, pattern_label):
        result = contains_sensitive_data(sensitive_text)
        assert result.is_sensitive
        assert result.pattern_matched == pattern_label
    
    def test_clean_technical_text_passes(self):
        text = "We should implement retry logic with exponential backoff."
        result = contains_sensitive_data(text)
        assert not result.is_sensitive
    
    def test_api_key_in_longer_text_detected(self):
        text = "Here's my API key: sk-abc123def456ghi789jkl012mno345pqr. Keep it safe."
        result = contains_sensitive_data(text)
        assert result.is_sensitive
```

### 2.2 Conflict Resolution Tests

```python
# tests/conflict/test_resolution.py

class TestTemporalResolution:
    
    def test_newer_node_wins(self, node_factory):
        older = node_factory(
            content="Backend: PostgreSQL",
            created_at=datetime(2025, 6, 1),
            user_verified=False
        )
        newer = node_factory(
            content="Backend: MongoDB",
            created_at=datetime(2025, 6, 15),
            user_verified=False
        )
        conflict = ConflictCandidate(node_a=older, node_b=newer, 
                                     conflict_type=ConflictType.DIRECT_FACT)
        
        result = resolve_temporal(conflict)
        
        assert result.resolved
        assert result.winning_node.id == newer.id
        assert result.archived_nodes[0].id == older.id
        assert older.valid_until is not None
        assert older.status == NodeStatus.SUPERSEDED
    
    def test_user_verified_node_requires_review(self, node_factory):
        user_node = node_factory(content="Backend: PostgreSQL", user_verified=True)
        system_node = node_factory(content="Backend: MongoDB", user_verified=False)
        
        conflict = ConflictCandidate(node_a=user_node, node_b=system_node,
                                     conflict_type=ConflictType.DIRECT_FACT)
        
        result = resolve_temporal(conflict)
        assert not result.resolved
        assert result.needs_review
    
    def test_resolution_creates_audit_event(self, node_factory, audit_log):
        older = node_factory(content="Decision A", created_at=datetime(2025, 6, 1))
        newer = node_factory(content="Decision B", created_at=datetime(2025, 6, 15))
        
        conflict = ConflictCandidate(node_a=older, node_b=newer,
                                     conflict_type=ConflictType.DIRECT_FACT)
        resolve_temporal(conflict)
        
        events = audit_log.get_events(action="conflict_resolved")
        assert len(events) == 1
        assert events[0].details['strategy'] == 'temporal'


class TestDecaySystem:
    
    def test_permanent_nodes_never_decay(self, node_factory):
        node = node_factory(importance_score=0.9, is_permanent=True)
        
        # Simulate 1 year passing
        node.last_accessed = datetime.utcnow() - timedelta(days=365)
        retention = compute_retention(node)
        
        # Permanent nodes should always return 1.0 retention
        assert retention == 1.0
    
    def test_old_unaccessed_node_decays(self, node_factory):
        node = node_factory(
            importance_score=0.5,
            decay_rate=0.05,
            is_permanent=False,
            last_accessed=datetime.utcnow() - timedelta(days=90)
        )
        retention = compute_retention(node)
        assert retention < 0.4  # Should be in archive territory
    
    def test_highly_reinforced_node_resists_decay(self, node_factory):
        node = node_factory(
            importance_score=0.7,
            decay_rate=0.05,
            reinforcement_count=15,
            last_accessed=datetime.utcnow() - timedelta(days=30)
        )
        retention = compute_retention(node)
        assert retention > 0.6  # Should survive despite time passing
```

### 2.3 API Layer Tests

```python
# tests/api/test_capture_endpoint.py

class TestCaptureEndpoint:
    
    @pytest.fixture
    def client(self):
        return TestClient(app)
    
    def test_valid_capture_returns_202(self, client, auth_headers):
        payload = {
            "session_id": "sess_test001",
            "platform": "claude",
            "user_message": "We decided to use FastAPI for the backend",
            "ai_response": "That's a solid choice for Python APIs...",
            "timestamp": "2025-06-07T10:30:00Z",
            "tab_url": "https://claude.ai/chat/test"
        }
        response = client.post("/api/v1/capture", json=payload, headers=auth_headers)
        assert response.status_code == 202
        assert response.json()["status"] == "queued"
    
    def test_sensitive_data_returns_blocked(self, client, auth_headers):
        payload = {
            "session_id": "sess_test002",
            "platform": "claude",
            "user_message": "My OpenAI key is sk-abc123def456ghi789jkl012mno345pqr",
            "ai_response": "I can help with that...",
            "timestamp": "2025-06-07T10:30:00Z",
            "tab_url": "https://claude.ai/chat/test"
        }
        response = client.post("/api/v1/capture", json=payload, headers=auth_headers)
        assert response.status_code == 202
        assert response.json()["status"] == "blocked"
        assert response.json()["reason"] == "sensitive_data_detected"
    
    def test_missing_auth_returns_401(self, client):
        response = client.post("/api/v1/capture", json={})
        assert response.status_code == 401
    
    def test_message_too_long_returns_413(self, client, auth_headers):
        payload = {
            "session_id": "sess_test003",
            "platform": "claude",
            "user_message": "x" * 60000,  # Exceeds 50,000 char limit
            "ai_response": "response",
            "timestamp": "2025-06-07T10:30:00Z",
            "tab_url": "https://claude.ai/chat/test"
        }
        response = client.post("/api/v1/capture", json=payload, headers=auth_headers)
        assert response.status_code == 413
```

### 2.4 TypeScript Extension Tests

```typescript
// tests/extraction/sensitiveDataFilter.test.ts

describe('SensitiveDataFilter', () => {
    test('detects API keys', () => {
        const text = 'Here is my key: sk-abc123def456ghi789jkl012mno345pqr';
        expect(containsSensitiveData(text)).toBe(true);
    });

    test('passes clean text', () => {
        const text = 'We decided to use FastAPI for the backend service.';
        expect(containsSensitiveData(text)).toBe(false);
    });
    
    test('detects credit cards', () => {
        const text = 'Card number: 4532 1234 5678 9012';
        expect(containsSensitiveData(text)).toBe(true);
    });
});

describe('WorkspaceDetector', () => {
    test('selects highest scoring workspace above threshold', async () => {
        const workspaces = [
            { id: 'ws_001', score: 0.82 },
            { id: 'ws_002', score: 0.45 },
        ];
        const result = await selectWorkspace(workspaces, threshold=0.55);
        expect(result.workspaceId).toBe('ws_001');
    });
    
    test('returns SUGGEST_NEW when all scores below threshold', async () => {
        const workspaces = [
            { id: 'ws_001', score: 0.42 },
            { id: 'ws_002', score: 0.38 },
        ];
        const result = await selectWorkspace(workspaces, threshold=0.55);
        expect(result.action).toBe('SUGGEST_NEW_WORKSPACE');
    });
});
```

---

## 3. INTEGRATION TESTS

**Target:** All service interactions, database operations, full pipeline flows

```python
# tests/integration/test_capture_pipeline.py

class TestFullCapturePipeline:
    """
    End-to-end capture pipeline test with real SQLite (in-memory) and mocked LLM.
    """
    
    @pytest.fixture
    def pipeline(self, tmp_path):
        """Set up a full pipeline with test databases."""
        workspace = create_test_workspace(tmp_path)
        return CaptureTestHarness(workspace, tmp_path)
    
    @pytest.mark.asyncio
    async def test_decision_is_extracted_and_committed(self, pipeline):
        capture = CaptureEvent(
            session_id="sess_001",
            platform="claude",
            user_message="We decided to use SQLite instead of PostgreSQL for local storage.",
            ai_response="SQLite makes sense for a local-first application...",
            timestamp=datetime.utcnow(),
            tab_url="https://claude.ai/chat/test"
        )
        
        result = await pipeline.process(capture)
        
        assert len(result.auto_committed) >= 1
        committed = result.auto_committed[0]
        assert committed.node_type == NodeType.DECISION
        assert "SQLite" in committed.content
        
        # Verify it's in the database
        db_node = pipeline.db.get_node(committed.id)
        assert db_node is not None
        assert db_node.status == NodeStatus.ACTIVE
    
    @pytest.mark.asyncio
    async def test_low_confidence_goes_to_pending_review(self, pipeline):
        capture = CaptureEvent(
            user_message="Maybe we should think about adding authentication...",
            ai_response="Authentication is definitely something to consider...",
            # ...
        )
        
        result = await pipeline.process(capture)
        
        # Speculative content should go to review, not auto-commit
        assert len(result.pending_review) > 0
        assert all(r.candidate_confidence < 0.80 for r in result.pending_review)
    
    @pytest.mark.asyncio
    async def test_conflict_detected_on_contradicting_extraction(self, pipeline):
        # First: establish a fact
        await pipeline.process(CaptureEvent(
            user_message="Our database is PostgreSQL",
            ai_response="Good choice for relational data.",
            # ...
        ))
        
        # Then: contradict it
        await pipeline.process(CaptureEvent(
            user_message="We switched to MongoDB last week",
            ai_response="MongoDB gives you more flexibility for this use case.",
            # ...
        ))
        
        conflicts = pipeline.db.get_conflicts(status='PENDING')
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == ConflictType.DIRECT_FACT


class TestContextRetrieval:
    
    @pytest.mark.asyncio
    async def test_active_goals_always_included(self, workspace_with_data):
        service = RetrievalService(workspace_with_data)
        
        result = await service.get_context(
            workspace_id=workspace_with_data.id,
            token_budget=2000
        )
        
        assert any("goal" in item.lower() for item in result.context_string.split('\n'))
    
    @pytest.mark.asyncio
    async def test_context_respects_token_budget(self, workspace_with_data):
        service = RetrievalService(workspace_with_data)
        
        result = await service.get_context(
            workspace_id=workspace_with_data.id,
            token_budget=500  # Very tight budget
        )
        
        assert result.token_count <= 500
    
    @pytest.mark.asyncio
    async def test_no_cross_workspace_contamination(self, two_workspaces):
        ws_a, ws_b = two_workspaces
        service = RetrievalService()
        
        result = await service.get_context(workspace_id=ws_a.id, token_budget=2000)
        
        # Context should only contain ws_a nodes
        node_ids = [n.id for n in result.nodes_included]
        assert all(
            service.graph.get_node(nid).workspace_id == ws_a.id
            for nid in node_ids
        )
```

---

## 4. MEMORY QUALITY TESTS

This is the most important test category. It measures whether Mnemosyne's extraction pipeline produces accurate, useful cognitive artifacts.

### 4.1 Benchmark Dataset Structure

```
tests/benchmarks/
├── samples/
│   ├── developer/          # 100 developer conversation pairs
│   ├── researcher/         # 100 researcher conversation pairs
│   ├── product/            # 100 product management conversations
│   ├── creative/           # 100 creative project conversations
│   └── edge_cases/         # 100 edge cases (hypotheticals, negations, ambiguous)
├── labels/
│   ├── developer.json      # Expected extractions for each sample
│   ├── researcher.json
│   └── ...
└── run_benchmarks.py
```

**Label format:**
```json
{
  "sample_id": "dev_042",
  "conversation": {
    "user": "We decided to remove offline mode from the MVP because the timeline is too tight.",
    "ai": "That makes sense given your hackathon deadline..."
  },
  "expected_extractions": [
    {
      "node_type": "decision",
      "content_contains": ["offline mode", "MVP"],
      "structured_data": {
        "rationale_contains": ["timeline", "deadline"]
      },
      "should_not_contain": ["offline mode added"],
      "min_confidence": 0.75
    }
  ],
  "should_not_extract": [
    "hackathon is fun"  // Too trivial, should be filtered
  ]
}
```

### 4.2 Benchmark Runner

```python
# tests/benchmarks/run_benchmarks.py

class ExtractionBenchmark:
    
    def run(self, category: str = 'all') -> BenchmarkReport:
        samples = load_samples(category)
        labels = load_labels(category)
        
        results = []
        for sample, label in zip(samples, labels):
            extracted = run_extraction_pipeline(sample)
            result = evaluate_extraction(extracted, label)
            results.append(result)
        
        return BenchmarkReport(
            total_samples=len(results),
            precision=self._compute_precision(results),
            recall=self._compute_recall(results),
            false_positive_rate=self._compute_fpr(results),
            by_node_type=self._compute_by_type(results),
            failed_samples=[r for r in results if not r.passed]
        )
    
    def _compute_precision(self, results: List[EvalResult]) -> float:
        """
        Precision = true positives / (true positives + false positives)
        """
        tp = sum(r.true_positives for r in results)
        fp = sum(r.false_positives for r in results)
        return tp / (tp + fp) if (tp + fp) > 0 else 0.0


# Expected benchmark results (from tests/benchmarks/targets.json):
BENCHMARK_TARGETS = {
    "overall_precision": 0.85,
    "overall_recall": 0.75,
    "false_positive_rate": 0.10,
    "by_type": {
        "decision": {"precision": 0.82, "recall": 0.78},
        "goal": {"precision": 0.88, "recall": 0.74},
        "technical_fact": {"precision": 0.91, "recall": 0.81},
        "entity": {"precision": 0.93, "recall": 0.86},
        "preference": {"precision": 0.79, "recall": 0.68},
    }
}

def test_extraction_meets_quality_targets():
    report = ExtractionBenchmark().run()
    
    assert report.precision >= BENCHMARK_TARGETS["overall_precision"], \
        f"Precision {report.precision:.2%} below target {BENCHMARK_TARGETS['overall_precision']:.2%}"
    
    assert report.recall >= BENCHMARK_TARGETS["overall_recall"], \
        f"Recall {report.recall:.2%} below target {BENCHMARK_TARGETS['overall_recall']:.2%}"
    
    assert report.false_positive_rate <= BENCHMARK_TARGETS["false_positive_rate"], \
        f"FPR {report.false_positive_rate:.2%} above target {BENCHMARK_TARGETS['false_positive_rate']:.2%}"
```

### 4.3 Retrieval Quality Tests

```python
class RetrievalQualityTest:
    """
    Tests that context reconstruction includes the right nodes for given scenarios.
    """
    
    def test_active_goals_retrieved_for_any_intent(self, workspace_fixture):
        """Active goals should always appear in context, regardless of query."""
        context = retrieve_context(workspace_fixture, intent="debug authentication bug")
        
        assert any(n.node_type == NodeType.GOAL and n.structured_data.get('status') == 'ACTIVE'
                   for n in context.nodes_included)
    
    def test_recent_decisions_retrieved_regardless_of_topic(self, workspace_fixture):
        """Decisions from last 7 days always in context."""
        recent_decision = workspace_fixture.get_recent_decision()  # Created yesterday
        context = retrieve_context(workspace_fixture, intent="unrelated topic")
        
        assert any(n.id == recent_decision.id for n in context.nodes_included)
    
    def test_superseded_nodes_not_retrieved(self, workspace_fixture):
        """Old, superseded facts must not appear in context."""
        superseded = workspace_fixture.get_superseded_node()
        context = retrieve_context(workspace_fixture)
        
        assert not any(n.id == superseded.id for n in context.nodes_included)
    
    def test_archived_workspace_nodes_not_contaminating_active(self, two_workspace_fixture):
        active_ws, archived_ws = two_workspace_fixture
        context = retrieve_context(active_ws)
        
        archived_ids = {n.id for n in archived_ws.get_nodes()}
        retrieved_ids = {n.id for n in context.nodes_included}
        
        assert len(archived_ids & retrieved_ids) == 0, "Cross-workspace contamination detected"
```

---

## 5. END-TO-END TESTS

**Tool:** Playwright (browser automation)  
**Environment:** Headless Chrome with test extension installed + test engine

```python
# tests/e2e/test_capture_flow.py

class TestCaptureE2E:
    
    @pytest.fixture
    def browser_with_extension(self, playwright, test_engine):
        """Launch Chrome with Mnemosyne extension installed in test mode."""
        browser = playwright.chromium.launch_persistent_context(
            user_data_dir=tmp_path,
            headless=True,
            args=[f'--load-extension={EXTENSION_BUILD_PATH}']
        )
        yield browser
    
    async def test_capture_fires_on_claude_message(self, browser_with_extension):
        page = await browser_with_extension.new_page()
        await page.goto("https://claude.ai/chat")  # Test environment mock
        
        # Simulate sending a message
        await page.fill('[data-testid="chat-input"]', 
                        "We decided to use FastAPI for this project")
        await page.click('[data-testid="send-button"]')
        
        # Wait for AI response (mocked in test environment)
        await page.wait_for_selector('[data-testid="ai-response"]', timeout=5000)
        
        # Wait for extraction to complete
        await asyncio.sleep(2)
        
        # Verify node was committed to test engine
        nodes = test_engine.get_nodes(workspace_id="ws_test")
        decisions = [n for n in nodes if n.node_type == NodeType.DECISION]
        assert len(decisions) >= 1
        assert "FastAPI" in decisions[0].content
    
    async def test_context_injection_visible_to_user(self, browser_with_extension):
        page = await browser_with_extension.new_page()
        
        # Pre-populate workspace with test data
        test_engine.create_test_nodes(workspace_id="ws_test")
        
        await page.goto("https://claude.ai/chat")
        
        # Injection indicator should appear
        indicator = await page.wait_for_selector('[data-testid="mnemosyne-injection-indicator"]')
        assert indicator is not None
        
        text = await indicator.inner_text()
        assert "Mnemosyne" in text
        assert "items" in text
    
    async def test_sensitive_data_not_stored(self, browser_with_extension, test_engine):
        page = await browser_with_extension.new_page()
        await page.goto("https://claude.ai/chat")
        
        initial_node_count = len(test_engine.get_nodes(workspace_id="ws_test"))
        
        # Send message with API key
        await page.fill('[data-testid="chat-input"]', 
                        "My API key is sk-abc123def456ghi789jkl012mno345pqr")
        await page.click('[data-testid="send-button"]')
        await asyncio.sleep(2)
        
        final_node_count = len(test_engine.get_nodes(workspace_id="ws_test"))
        
        # No new nodes should have been created
        assert final_node_count == initial_node_count
```

---

## 6. PERFORMANCE TESTS

```python
# tests/performance/test_latency.py

class TestLatencyTargets:
    
    @pytest.mark.benchmark
    async def test_retrieval_under_300ms(self, workspace_with_100_nodes, benchmark):
        service = RetrievalService(workspace_with_100_nodes)
        
        result = await benchmark.async_run(
            service.get_context,
            workspace_id=workspace_with_100_nodes.id,
            token_budget=2000
        )
        
        assert benchmark.stats['mean'] < 0.300  # 300ms
    
    @pytest.mark.benchmark
    def test_sensitive_data_filter_under_10ms(self, benchmark):
        text = "We decided to use FastAPI " * 100  # Large text
        
        result = benchmark.run(contains_sensitive_data, text)
        
        assert benchmark.stats['mean'] < 0.010  # 10ms
    
    @pytest.mark.benchmark
    async def test_extraction_pipeline_under_500ms(self, benchmark):
        capture = create_test_capture(
            message_length=2000  # Typical conversation turn
        )
        
        result = await benchmark.async_run(process_capture, capture)
        
        assert benchmark.stats['mean'] < 0.500  # 500ms
    
    @pytest.mark.benchmark
    def test_graph_query_5_hops_under_50ms(self, workspace_with_1000_nodes, benchmark):
        center_node = workspace_with_1000_nodes.get_random_node()
        
        result = benchmark.run(
            graph_traverse,
            center_node_id=center_node.id,
            max_hops=5
        )
        
        assert benchmark.stats['mean'] < 0.050  # 50ms
```

---

## 7. CI PIPELINE

```yaml
# .github/workflows/test.yml

jobs:
  unit-tests:
    runs-on: ubuntu-latest
    steps:
      - run: uv run pytest tests/unit/ -v --cov=src --cov-report=xml
      - run: pnpm vitest run tests/unit/

  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - run: uv run pytest tests/integration/ -v

  memory-quality-benchmarks:
    runs-on: ubuntu-latest
    steps:
      - run: uv run python tests/benchmarks/run_benchmarks.py
      - name: Fail if quality targets not met
        run: uv run pytest tests/benchmarks/test_quality_targets.py -v

  performance-tests:
    runs-on: ubuntu-latest
    steps:
      - run: uv run pytest tests/performance/ --benchmark-only

  e2e-tests:
    runs-on: ubuntu-latest
    steps:
      - run: pnpm build:extension:test
      - run: uv run pytest tests/e2e/ -v
```

**PR gates:**
- All unit tests must pass
- Integration tests must pass
- Memory quality benchmarks must meet targets (no regression allowed)
- Performance tests must not regress > 20% vs baseline

**Nightly only:**
- Full E2E suite (slow)
- Full benchmark suite across all 500 samples

---

## 8. TEST DATA MANAGEMENT

### 8.1 Synthetic Data Only
All test data is synthetically generated. No real user conversation data is ever used in tests.

### 8.2 Test Fixtures Pattern

```python
# tests/conftest.py

@pytest.fixture
def workspace_with_data(tmp_path) -> Workspace:
    """Creates a test workspace with 50 pre-populated nodes."""
    db_path = tmp_path / "test_graph.db"
    ws = create_workspace(db_path, name="Test Workspace")
    
    # Seed with representative data
    seed_test_nodes(ws, node_count=50, type_distribution={
        NodeType.GOAL: 5,
        NodeType.DECISION: 10,
        NodeType.TECHNICAL_FACT: 15,
        NodeType.ENTITY: 10,
        NodeType.TASK: 5,
        NodeType.PROBLEM: 5,
    })
    
    return ws

@pytest.fixture
def node_factory():
    """Factory for creating test nodes with sensible defaults."""
    def _factory(**kwargs) -> MemoryNode:
        defaults = {
            "id": generate_id(),
            "workspace_id": "ws_test",
            "node_type": NodeType.DECISION,
            "tier": MemoryTier.EPISODIC,
            "content": "Test decision content",
            "structured_data": {},
            "importance_score": 0.7,
            "extraction_confidence": 0.85,
            "user_verified": False,
            "status": NodeStatus.ACTIVE,
            "created_at": datetime.utcnow(),
            "valid_from": datetime.utcnow(),
            "valid_until": None,
            "version": 1,
            "reinforcement_count": 0,
            "decay_rate": 0.05,
            "is_permanent": False,
        }
        defaults.update(kwargs)
        return MemoryNode(**defaults)
    return _factory
```
