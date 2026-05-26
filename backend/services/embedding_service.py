"""Embeddings (fastembed, in-process ONNX) + Qdrant local vector store.

Per-workspace Qdrant collections live under workspaces/{id}/vectors/. Degrades
gracefully: if fastembed/qdrant are unavailable, semantic features are disabled
but the engine keeps running on FTS + structured retrieval.

Qdrant point IDs must be ints or UUIDs, so we derive a deterministic UUID from
each node_id (uuid5) and keep the real node_id in the payload.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from backend.config import MnemosyneConfig

logger = logging.getLogger("mnemosyne.embedding")

_NS = uuid.NAMESPACE_OID


def _point_id(node_id: str) -> str:
    return str(uuid.uuid5(_NS, node_id))


class EmbeddingService:
    COLLECTION = "memory"

    DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

    def __init__(self, config: MnemosyneConfig):
        self.config = config
        self._model = None
        self._dim: Optional[int] = None  # actual dim of the loaded model
        self._clients: dict[str, object] = {}
        self._available = True
        try:
            from fastembed import TextEmbedding  # noqa: PLC0415

            self._TextEmbedding = TextEmbedding
        except ImportError:
            self._available = False
            logger.warning("fastembed unavailable - semantic features disabled")

    @property
    def available(self) -> bool:
        return self._available

    def _ensure_model(self) -> None:
        if self._model is not None or not self._available:
            return
        name = self.config.embedding_model
        # Validate against fastembed's catalog; fall back if the configured name
        # is unknown (e.g. a stale config from an earlier default like "bge-m3").
        try:
            supported = {m["model"] for m in self._TextEmbedding.list_supported_models()}
            if supported and name not in supported:
                logger.warning("embedding model %r unsupported by fastembed; using %s", name, self.DEFAULT_MODEL)
                name = self.DEFAULT_MODEL
        except Exception:  # noqa: BLE001 - catalog lookup is best-effort
            pass
        self._model = self._TextEmbedding(model_name=name)
        # Derive the true dimension from the model so the Qdrant collection can
        # never mismatch what we actually produce (config.embedding_dim is a hint).
        self._dim = len(next(iter(self._model.embed(["dimension probe"]))).tolist())

    def embed(self, text: str) -> Optional[list[float]]:
        if not self._available:
            return None
        self._ensure_model()
        vec = next(iter(self._model.embed([text])))  # type: ignore[union-attr]
        return vec.tolist()

    def _coll(self, workspace_id: str) -> str:
        # Local mode isolates per workspace by directory, so one constant name is
        # fine. A shared server holds all workspaces, so the name carries the id.
        return f"ws_{workspace_id}" if self.config.qdrant_url else self.COLLECTION

    def _client(self, workspace_id: str):
        from qdrant_client import QdrantClient, models  # noqa: PLC0415

        self._ensure_model()  # guarantees self._dim matches the real model
        dim = self._dim or self.config.embedding_dim
        coll = self._coll(workspace_id)

        if self.config.qdrant_url:
            # Server mode: one shared client; on-disk + int8 quantization are
            # genuinely honored here, removing the RAM ceiling for huge memory sets.
            client = self._clients.get("__server__")
            if client is None:
                client = QdrantClient(url=self.config.qdrant_url)
                self._clients["__server__"] = client
        else:
            # Local mode (default, no daemon).
            client = self._clients.get(workspace_id)
            if client is None:
                path = self.config.data_dir / "workspaces" / workspace_id / "vectors"
                path.mkdir(parents=True, exist_ok=True)
                client = QdrantClient(path=str(path))
                self._clients[workspace_id] = client

        if not client.collection_exists(coll):
            client.create_collection(
                coll,
                # on_disk keeps raw vectors off the heap; int8 scalar quantization
                # (kept in RAM for fast search) is ~4x smaller than float32. Both are
                # honored by a Qdrant server; local mode accepts them harmlessly.
                vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE, on_disk=True),
                quantization_config=models.ScalarQuantization(
                    scalar=models.ScalarQuantizationConfig(type=models.ScalarType.INT8, always_ram=True)
                ),
            )
        return client

    def embed_and_store(self, workspace_id: str, node_id: str, text: str, payload: dict) -> Optional[str]:
        """Embed text, upsert into the workspace collection. Returns the point id."""
        if not self._available:
            return None
        vec = self.embed(text)
        from qdrant_client import models  # noqa: PLC0415

        pid = _point_id(node_id)
        self._client(workspace_id).upsert(
            self._coll(workspace_id),
            points=[models.PointStruct(id=pid, vector=vec, payload={**payload, "node_id": node_id})],
        )
        return pid

    def search(
        self,
        workspace_id: str,
        query_text: str,
        top_k: int = 10,
        exclude_node_id: Optional[str] = None,
        score_threshold: float = 0.0,
    ) -> list[tuple[str, float]]:
        """Return [(node_id, score)] for the most similar nodes."""
        if not self._available:
            return []
        vec = self.embed(query_text)
        return self.search_by_vector(workspace_id, vec, top_k, exclude_node_id, score_threshold)

    def search_by_vector(
        self,
        workspace_id: str,
        vector: list[float],
        top_k: int = 10,
        exclude_node_id: Optional[str] = None,
        score_threshold: float = 0.0,
    ) -> list[tuple[str, float]]:
        if not self._available or vector is None:
            return []
        client = self._client(workspace_id)
        res = client.query_points(
            self._coll(workspace_id), query=vector, limit=top_k + 1, score_threshold=score_threshold
        ).points
        out: list[tuple[str, float]] = []
        for p in res:
            nid = (p.payload or {}).get("node_id")
            if nid and nid != exclude_node_id:
                out.append((nid, p.score))
        return out[:top_k]

    def similarity(self, text_a: str, text_b: str) -> float:
        """Cosine similarity between two texts (0.0 if embeddings unavailable)."""
        va, vb = self.embed(text_a), self.embed(text_b)
        if not va or not vb:
            return 0.0
        import math  # noqa: PLC0415

        dot = sum(x * y for x, y in zip(va, vb))
        na = math.sqrt(sum(x * x for x in va))
        nb = math.sqrt(sum(y * y for y in vb))
        return dot / (na * nb) if na and nb else 0.0

    def delete(self, workspace_id: str, node_id: str) -> None:
        if not self._available:
            return
        from qdrant_client import models  # noqa: PLC0415

        self._client(workspace_id).delete(
            self._coll(workspace_id),
            points_selector=models.PointIdsList(points=[_point_id(node_id)]),
        )

    def close(self) -> None:
        for client in self._clients.values():
            try:
                client.close()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
        self._clients.clear()
