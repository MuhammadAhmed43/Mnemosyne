"""Labeled extraction cases — the ground truth for measuring pipeline quality.

Each case is one conversation turn (user + AI) with:
  expect          : extractions that SHOULD be produced (recall). A prediction
                    matches when node_type is equal and every `contains` keyword
                    appears in the candidate content (case-insensitive).
  expect_absent   : substrings that must NOT appear in any committed/pending
                    decision/goal/technical_fact (precision — guards against
                    hypotheticals, negations, and noise becoming "facts").
  expect_empty    : True when the turn should yield no extractions at all.

Add new cases freely — this file is the spec for "good extraction." Keep inputs
realistic and combined length > 50 chars (shorter turns are skipped as trivial).
"""

from __future__ import annotations

CASES: list[dict] = [
    # ---- decisions (firm commitments) ----
    {
        "name": "explicit decision with rationale",
        "user": "We decided to use FastAPI for the backend because we need async support.",
        "ai": "Good call — FastAPI's async model fits that well.",
        "expect": [{"type": "decision", "contains": ["fastapi"]}],
    },
    {
        "name": "firm choice: let's go with",
        "user": "Let's go with PostgreSQL for the database layer.",
        "ai": "PostgreSQL is a solid choice for relational data with strong consistency.",
        "expect": [{"type": "decision", "contains": ["postgresql"]}],
    },
    {
        "name": "firm choice: let's work with",
        "user": "Okay, let's work with Kubernetes for the orchestrator.",
        "ai": "Great — a small Kubernetes-style orchestrator is a strong portfolio project.",
        "expect": [{"type": "decision", "contains": ["kubernetes"]}],
    },
    # ---- goals (aspirational first-person intent) ----
    {
        "name": "first-person goal: i want to",
        "user": "I want to work on a mini container orchestrator in Go.",
        "ai": "That's a great project. You'd implement scheduling, health checks, and a control loop.",
        "expect": [{"type": "goal", "contains": ["work on"]}],
    },
    {
        "name": "explicit goal statement",
        "user": "My goal is to ship the beta by Friday.",
        "ai": "Tight but doable — prioritize the core checkout flow first.",
        "expect": [{"type": "goal", "contains": ["ship"]}],
    },
    # ---- technical facts ----
    {
        "name": "tech fact from 'using'",
        "user": "We're using Redis for the cache and Stripe for payments.",
        "ai": "Redis is great for caching; Stripe handles payments well.",
        "expect": [{"type": "technical_fact", "contains": ["redis"]}],
    },
    # ---- problems ----
    {
        "name": "open problem",
        "user": "We're blocked on the OAuth callback — it keeps returning a 500 error.",
        "ai": "That's usually a redirect-URI mismatch. Check the registered callback URL.",
        "expect": [{"type": "problem", "contains": ["oauth"]}],
    },
    # ---- preferences ----
    {
        "name": "preference",
        "user": "I prefer concise answers with no fluff, just the code.",
        "ai": "Understood — I'll keep responses tight and code-focused.",
        "expect": [{"type": "preference", "contains": ["concise"]}],
    },
    # ---- ideas / brainstorming -> insight ----
    {
        "name": "idea elaboration",
        "user": "Tell me more about the meal-prep subscription idea and how it would work.",
        "ai": "A meal-prep subscription delivers pre-portioned ingredients weekly. Customers pick "
              "recipes online, you bulk-source ingredients, and a fulfillment partner ships chilled "
              "boxes. Revenue is a recurring weekly fee with tiered plans.",
        "expect": [{"type": "insight", "contains": ["meal-prep"]}],
    },
    {
        "name": "info-seeking idea capture",
        "user": "Is there an app that turns a topic into a ready-to-read meeting script?",
        "ai": "Yes — several tools generate structured talking points and scripts from a topic. "
              "You give it the subject and audience, and it produces an agenda plus a word-for-word "
              "script you can read from, with sections you can tweak.",
        "expect": [{"type": "insight", "contains": []}],
    },
    # ---- precision guards: must NOT extract ----
    {
        "name": "hypothetical is not a decision",
        "user": "What if we used MongoDB instead of Postgres? Just brainstorming.",
        "ai": "MongoDB would change your data model to documents; consider the tradeoffs first.",
        "expect": [],
        "expect_absent": ["mongodb"],
    },
    {
        "name": "negation is not a fact",
        "user": "We are not going to use Redis — it's overkill for our scale.",
        "ai": "Fair — an in-process cache is simpler at small scale.",
        "expect": [],
        "expect_absent": ["redis"],
    },
    {
        "name": "AI-suggested options are not committed facts",
        "user": "what database should the app use?",
        "ai": "You could use PostgreSQL for relational data, or MongoDB for documents; "
              "popular options also include Firebase for quick prototypes.",
        "expect": [],
        "expect_absent": ["mongodb", "firebase"],
    },
    {
        "name": "trivial chatter yields nothing",
        "user": "thanks, that's super helpful!",
        "ai": "You're welcome — glad it helped!",
        "expect": [],
        "expect_empty": True,
    },
]
