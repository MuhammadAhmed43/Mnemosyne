"""Shared pytest fixtures. Each container gets an isolated temp data dir so
tests never touch real user data and never collide."""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(scope="session", autouse=True)
def _safe_appdata():
    # Fallback so nothing writes to the real APPDATA even outside `container`.
    base = tempfile.mkdtemp(prefix="mnemo_session_")
    os.environ["APPDATA"] = os.path.join(base, "appdata")
    yield


@pytest.fixture
def container(tmp_path):
    os.environ["APPDATA"] = str(tmp_path / "appdata")
    from backend.config import MnemosyneConfig
    from backend.container import ServiceContainer

    c = ServiceContainer(MnemosyneConfig.create_default())
    yield c
    c.shutdown()


@pytest.fixture
def workspace(container):
    return container.workspace_service.create("Test Workspace", "pytest workspace")


@pytest.fixture
def node_factory():
    from backend.models.enums import NodeType
    from backend.models.memory_node import MemoryNode

    def make(**kw):
        defaults = dict(workspace_id="ws_test", node_type=NodeType.DECISION, content="test content")
        defaults.update(kw)
        return MemoryNode(**defaults)

    return make
