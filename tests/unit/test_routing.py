"""Workspace routing: a URL pin must not trap an unrelated new topic typed into
an already-pinned chat, but should still anchor empty context-injection probes."""

from __future__ import annotations


def test_url_pin_yields_to_offtopic_content(container):
    svc = container.workspace_service
    a = svc.create("Networking", "http and networking internals")
    svc.create("Other", "unrelated")
    svc.remember_mapping("chatgpt", a.id, "https://chatgpt.com/c/pinned-abc")

    container.embedding._available = True
    container.embedding.similarity = lambda x, y: 0.1  # everything looks off-topic

    # A substantive, off-topic turn in the pinned chat must NOT be forced into A.
    wsid, _ = svc.infer_workspace(
        "i want to build a sports goods selling application",
        "Here is how a sports goods marketplace app could work …",
        "https://chatgpt.com/c/pinned-abc",
    )
    assert wsid != a.id  # pin ignored; low similarity everywhere -> needs a new workspace

    # An empty context-injection probe on the same URL still anchors to the pin.
    wsid2, _ = svc.infer_workspace("", "", "https://chatgpt.com/c/pinned-abc")
    assert wsid2 == a.id


def test_new_project_declaration_makes_new_workspace(container):
    from backend.services.workspace_service import is_new_project_declaration

    for msg in (
        "i want to work on an app for blind people",
        "i want to make an application for sports good selling",
        "i want to work on a game called moneydev",
        "let's build a marketplace for sports gear",
    ):
        assert is_new_project_declaration(msg), msg
    assert not is_new_project_declaration("how does the http keep-alive work")

    svc = container.workspace_service
    a = svc.create("AI Engineer Prep", "preparing for an AI engineering career, projects")
    svc.remember_mapping("chatgpt", a.id, "https://chatgpt.com/c/pinned-xyz")
    container.embedding._available = True
    # Thematically adjacent (both 'tech projects') but NOT the same project.
    container.embedding.similarity = lambda x, y: 0.55

    wsid, _ = svc.infer_workspace(
        "i want to work on an app for blind people",
        "Here's how an accessibility-focused app for blind users could work …",
        "https://chatgpt.com/c/pinned-xyz",
    )
    # 0.55 < 0.70 reuse bar for a declared new project -> not reused, pin skipped.
    assert wsid != a.id


def test_url_pin_honored_when_content_fits(container):
    svc = container.workspace_service
    a = svc.create("Networking", "http and networking internals")
    svc.remember_mapping("chatgpt", a.id, "https://chatgpt.com/c/net-chat")

    container.embedding._available = True
    container.embedding.similarity = lambda x, y: 0.8  # on-topic for the pinned ws

    wsid, _ = svc.infer_workspace(
        "the keep-alive timeout on our HTTP client",
        "You can tune the connection pool …",
        "https://chatgpt.com/c/net-chat",
    )
    assert wsid == a.id  # related content -> pin honored
