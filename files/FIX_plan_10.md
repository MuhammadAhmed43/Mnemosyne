# FIX — Plan 10: Testing Strategy
## Fix for C-09
---

## HOW TO USE THIS FILE
Append the three missing test methods to the existing `TestLatencyTargets` class,
and add the RAM test class below it. Both go in `tests/performance/test_latency.py`.

---

## FIX C-09 — Performance benchmarks missing 3 operations + RAM test
**File to edit:** `tests/performance/test_latency.py`
**Location:** Inside and after the `TestLatencyTargets` class

Doc 14 §6 defines 8 performance targets. Plan 10 tests 5 of them. Three latency tests
and one RAM test are missing:

| Missing target | Threshold | Hard limit |
|---|---|---|
| Workspace switch | < 100ms | 300ms |
| Sidebar load | < 300ms | 500ms |
| Engine RAM at rest | < 150MB | 300MB |

The full-text search (`test_fts_under_100ms`) is already present — do not add it again.

### Step 1 — Append to `TestLatencyTargets` class

Add these three methods immediately after `test_fts_under_100ms` (still inside the class):

```python
    # ── Missing tests from Doc 14 §6 ──────────────────────────────────────────

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
```

### Step 2 — Add RAM test class below `TestLatencyTargets`

Add this as a separate class immediately after `TestLatencyTargets` ends:

```python
class TestMemoryUsage:
    """Doc 14 §6: Engine RAM usage at rest < 150MB target, 300MB hard limit.

    Measures the resident set size (RSS) of the engine process after startup
    with no active captures or retrievals in flight.
    """

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

### Step 3 — Add the required fixtures (if not already present)

Add these to `tests/conftest.py` or `tests/performance/conftest.py`:

```python
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

**Why:** Doc 14 §6 defines a performance law table with 8 required operations and their
targets. The plan covers 5: context injection, extraction, graph query, sensitive filter,
and full-text search. Missing are workspace switch (< 100ms), sidebar load (< 300ms), and
engine RAM at rest (< 300MB hard limit). Doc 14 §1 says "Benchmark these on every release —
performance regressions are bugs." Without the missing tests, regressions in workspace
switching and RAM will not be caught in CI. (Ref: Doc 14 §6, C-09 conflict report)

---

## No other changes needed in Plan 10.
