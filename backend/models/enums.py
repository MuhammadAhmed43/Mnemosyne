"""All enumerations for Mnemosyne (Doc 04 §2.2, Doc 05 §2, Doc 07).

Plan 01 extends the spec's closed sets with a few additional types that
downstream plans reference (e.g. NodeStatus.DECAYED used by the decay service,
INSIGHT/CONSTRAINT used by the importance scorer). Every value here MUST be
mirrored in the matching SQL CHECK constraint in db/schema.py.
"""

from enum import Enum


class NodeType(str, Enum):
    # Core cognitive types (Doc 04 §2.2)
    GOAL = "goal"
    DECISION = "decision"
    TASK = "task"
    PROBLEM = "problem"
    EVENT = "event"

    # Knowledge types
    TECHNICAL_FACT = "technical_fact"
    ENTITY = "entity"
    PREFERENCE = "preference"
    RELATIONSHIP = "relationship"

    # Meta types
    WORKSPACE_SUMMARY = "workspace_summary"
    USER_NOTE = "user_note"

    # Plan additions (referenced by importance scorer / retrieval formatting)
    OPEN_QUESTION = "open_question"
    INSIGHT = "insight"
    HYPOTHESIS = "hypothesis"
    CONSTRAINT = "constraint"


class MemoryTier(str, Enum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class NodeStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"
    PENDING_REVIEW = "pending_review"
    DECAYED = "decayed"  # Plan addition — pruned cold storage (Doc 04 §8)


class EdgeType(str, Enum):
    # Doc 04 §2.3 core set
    RELATES_TO = "relates_to"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    PART_OF = "part_of"
    CAUSED_BY = "caused_by"
    ASSIGNED_TO = "assigned_to"
    RESOLVED_BY = "resolved_by"
    SIMILAR_TO = "similar_to"
    # Plan additions
    DERIVED_FROM = "derived_from"
    BLOCKED_BY = "blocked_by"
    SUPPORTS = "supports"


class ConflictType(str, Enum):
    # Doc 05 §2 — six canonical types
    DIRECT_FACT = "direct_fact"
    GOAL_STATE = "goal_state"
    SEMANTIC_DRIFT = "semantic_drift"
    PREFERENCE = "preference"
    LOGICAL_ERROR = "logical_error"
    ENTITY_DISAMBIGUATION = "entity_disambiguation"
    # Plan refinements
    GOAL_CONFLICT = "goal_conflict"
    VERSION_FORK = "version_fork"
    SCOPE_CONTRADICTION = "scope_contradiction"
    LOGICAL_INCONSISTENCY = "logical_inconsistency"


class ConflictStrategy(str, Enum):
    TEMPORAL = "temporal"
    CONFIDENCE_WEIGHTED = "confidence"
    USER_REVIEW = "user_review"
    PREFERENCE_MERGE = "preference_merge"
    LOGICAL_FLAG = "logical_flag"


class ResolutionStatus(str, Enum):
    PENDING = "pending"
    AUTO_RESOLVED = "auto_resolved"
    USER_RESOLVED = "user_resolved"
    DISMISSED = "dismissed"


class CaptureStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"
    FAILED = "failed"


class Platform(str, Enum):
    CLAUDE = "claude"
    CHATGPT = "chatgpt"
    GEMINI = "gemini"
    MANUAL = "manual"


class WorkspaceStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    PAUSED = "paused"
    DELETED = "deleted"  # C-01: must be in SQL CHECK too


class CandidateStatus(str, Enum):
    AUTO_COMMITTED = "auto_committed"
    PENDING_REVIEW = "pending_review"
    DISCARDED = "discarded"
    USER_APPROVED = "user_approved"
    USER_REJECTED = "user_rejected"
