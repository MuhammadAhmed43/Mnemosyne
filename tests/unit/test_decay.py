"""Unit tests for decay retention (Doc 04 §8). compute_retention needs no repos."""

from __future__ import annotations

from datetime import timedelta

from backend.models.enums import NodeType
from backend.services.decay_service import DecayService
from backend.utils.time import now_utc

svc = DecayService(None, None, None)  # type: ignore[arg-type]  # retention math only


def test_permanent_never_decays(node_factory):
    n = node_factory(is_permanent=True, importance_score=0.9, last_accessed=now_utc() - timedelta(days=365))
    assert svc.compute_retention(n) == 1.0


def test_old_unaccessed_decays(node_factory):
    n = node_factory(node_type=NodeType.EVENT, importance_score=0.5, decay_rate=0.08,
                     last_accessed=now_utc() - timedelta(days=120))
    assert svc.compute_retention(n) < 0.4


def test_reinforced_resists_decay(node_factory):
    n = node_factory(node_type=NodeType.DECISION, importance_score=0.7, decay_rate=0.05,
                     reinforcement_count=15, last_accessed=now_utc() - timedelta(days=30))
    assert svc.compute_retention(n) > 0.6


def test_archived_workspace_lowers_retention(node_factory):
    n = node_factory(importance_score=0.7, decay_rate=0.02, last_accessed=now_utc() - timedelta(days=5))
    active = svc.compute_retention(n, "active")
    archived = svc.compute_retention(n, "archived")
    assert archived < active
