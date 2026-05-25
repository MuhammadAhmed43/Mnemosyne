"""Service container — wires shared singletons and builds workspace-scoped
services on demand.

Most services are workspace-scoped (their repositories bind to a specific
graph.db connection), so they can't be plain app-wide singletons. Shared,
stateless/global pieces (config, db manager, embedding model, intent, pipeline,
global repos, workspace/onboarding/capture services) are built once; per-workspace
services are constructed per call from the cached connection (cheap).
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Plan-12 extras are lazy-imported in their factory methods to
    # avoid heavy/circular imports; declare them here only for type checkers.
    from backend.repositories.feedback_repo import FeedbackRepository
    from backend.repositories.thread_repo import ThreadRepository
    from backend.services.feedback_service import FeedbackService
    from backend.services.graph_diff_service import GraphDiffService
    from backend.services.merge_service import WorkspaceMergeService
    from backend.services.nl_query_service import NaturalLanguageQueryService
    from backend.services.snapshot_service import SnapshotService

from backend.config import MnemosyneConfig
from backend.db.manager import DatabaseManager
from backend.extraction.pipeline import ExtractionPipeline
from backend.repositories.audit_repo import AuditRepository
from backend.repositories.conflict_repo import ConflictRepository
from backend.repositories.edge_repo import EdgeRepository
from backend.repositories.node_repo import NodeRepository
from backend.repositories.onboarding_repo import OnboardingRepository
from backend.repositories.pending_review_repo import PendingReviewRepository
from backend.repositories.session_repo import SessionRepository
from backend.repositories.settings_repo import SettingsRepository
from backend.repositories.workspace_repo import WorkspaceRepository
from backend.services.capture_service import CaptureService
from backend.services.conflict_service import ConflictService
from backend.services.consolidation_service import ConsolidationService
from backend.services.decay_service import DecayService
from backend.services.embedding_service import EmbeddingService
from backend.services.graph_service import GraphService
from backend.services.intent_service import IntentService
from backend.services.onboarding_service import OnboardingService
from backend.services.retrieval_service import RetrievalService
from backend.services.workspace_service import WorkspaceService


class ServiceContainer:
    def __init__(self, config: MnemosyneConfig):
        self.config = config
        self.db = DatabaseManager(config)

        # Shared singletons
        self.embedding = EmbeddingService(config)
        self.intent = IntentService()
        self.pipeline = ExtractionPipeline(config)
        self.events: asyncio.Queue[dict] = asyncio.Queue()  # producers publish here
        # Each connected WS client registers a queue here; a broadcaster task
        # (started in the app lifespan) fans every event out to all of them, so
        # the dashboard AND the chat tab can both receive live updates.
        self.subscribers: set[asyncio.Queue[dict]] = set()

        # Global-scoped repos (global.db)
        gconn = self.db.get_global()
        self.workspace_repo = WorkspaceRepository(gconn)
        self.audit_repo = AuditRepository(gconn)
        self.settings_repo = SettingsRepository(gconn)
        self.onboarding_repo = OnboardingRepository(gconn)

        # Global-scoped services
        self.workspace_service = WorkspaceService(
            self.db, self.workspace_repo, self.embedding, self.audit_repo, config
        )
        self.onboarding_service = OnboardingService(self.onboarding_repo)
        self.capture_service = CaptureService(self.workspace_service, self.db, self.settings_repo)

    # ---- per-workspace repositories ---- #
    def node_repo(self, ws: str) -> NodeRepository:
        return NodeRepository(self.db.get_workspace(ws))

    def edge_repo(self, ws: str) -> EdgeRepository:
        return EdgeRepository(self.db.get_workspace(ws))

    def conflict_repo(self, ws: str) -> ConflictRepository:
        return ConflictRepository(self.db.get_workspace(ws))

    def pending_repo(self, ws: str) -> PendingReviewRepository:
        return PendingReviewRepository(self.db.get_workspace(ws))

    def session_repo(self, ws: str) -> SessionRepository:
        return SessionRepository(self.db.get_workspace(ws))

    # ---- per-workspace services ---- #
    def graph_service(self, ws: str) -> GraphService:
        return GraphService(self.node_repo(ws), self.edge_repo(ws), self.audit_repo, self.embedding)

    def conflict_service(self, ws: str) -> ConflictService:
        return ConflictService(self.node_repo(ws), self.edge_repo(ws), self.conflict_repo(ws), self.embedding)

    def retrieval_service(self, ws: str) -> RetrievalService:
        return RetrievalService(
            self.node_repo(ws), self.conflict_repo(ws), self.embedding, self.workspace_repo, self.intent
        )

    def decay_service(self, ws: str) -> DecayService:
        return DecayService(self.node_repo(ws), self.workspace_repo, self.audit_repo)

    def consolidation_service(self, ws: str) -> ConsolidationService:
        return ConsolidationService(self.node_repo(ws), self.edge_repo(ws), self.embedding, self.audit_repo)

    # ---- Plan 12 extras ---- #
    def thread_repo(self, ws: str) -> "ThreadRepository":
        from backend.repositories.thread_repo import ThreadRepository

        return ThreadRepository(self.db.get_workspace(ws))

    def feedback_repo(self, ws: str) -> "FeedbackRepository":
        from backend.repositories.feedback_repo import FeedbackRepository

        return FeedbackRepository(self.db.get_workspace(ws))

    def snapshot_service(self, ws: str) -> "SnapshotService":
        from backend.services.snapshot_service import SnapshotService

        return SnapshotService(self.node_repo(ws), self.workspace_repo)

    def graph_diff_service(self, ws: str) -> "GraphDiffService":
        from backend.services.graph_diff_service import GraphDiffService

        return GraphDiffService(self.node_repo(ws), self.conflict_repo(ws))

    def feedback_service(self, ws: str) -> "FeedbackService":
        from backend.services.feedback_service import FeedbackService

        return FeedbackService(self.feedback_repo(ws))

    def nl_query_service(self, ws: str) -> "NaturalLanguageQueryService":
        from backend.services.nl_query_service import NaturalLanguageQueryService

        return NaturalLanguageQueryService(self.node_repo(ws), self.embedding)

    @property
    def merge_service(self) -> "WorkspaceMergeService":
        from backend.services.merge_service import WorkspaceMergeService

        return WorkspaceMergeService(self.db, self.workspace_repo, self.embedding)

    def shutdown(self) -> None:
        self.embedding.close()
        self.db.close_all()
