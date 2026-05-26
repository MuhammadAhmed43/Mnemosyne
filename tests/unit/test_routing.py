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
