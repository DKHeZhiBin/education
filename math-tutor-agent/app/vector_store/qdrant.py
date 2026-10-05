from __future__ import annotations

from qdrant_client import QdrantClient, models

from app.core.config import Settings, settings
from app.domain.vector_store import CollectionProvisionResult, VectorPoint


FILTER_FIELDS: dict[str, models.PayloadSchemaType] = {
    "schema_version": models.PayloadSchemaType.KEYWORD,
    "index_status": models.PayloadSchemaType.KEYWORD,
    "content_status": models.PayloadSchemaType.KEYWORD,
    "evaluation_only": models.PayloadSchemaType.BOOL,
    "entity_type": models.PayloadSchemaType.KEYWORD,
    "entity_id": models.PayloadSchemaType.KEYWORD,
    "subject": models.PayloadSchemaType.KEYWORD,
    "grade_band": models.PayloadSchemaType.KEYWORD,
    "grade_codes": models.PayloadSchemaType.KEYWORD,
    "knowledge_point_codes": models.PayloadSchemaType.KEYWORD,
    "problem_types": models.PayloadSchemaType.KEYWORD,
    "content_types": models.PayloadSchemaType.KEYWORD,
    "difficulty": models.PayloadSchemaType.INTEGER,
    "difficulty_sources": models.PayloadSchemaType.KEYWORD,
    "curriculum_version": models.PayloadSchemaType.KEYWORD,
    "curriculum_version_id": models.PayloadSchemaType.KEYWORD,
    "language": models.PayloadSchemaType.KEYWORD,
    "disclosure_level": models.PayloadSchemaType.INTEGER,
    "hint_level": models.PayloadSchemaType.INTEGER,
    "generation_batch_id": models.PayloadSchemaType.KEYWORD,
    "verification_level": models.PayloadSchemaType.KEYWORD,
    "verifier_version_ids": models.PayloadSchemaType.KEYWORD,
    "embedding_model": models.PayloadSchemaType.KEYWORD,
    "index_version": models.PayloadSchemaType.KEYWORD,
}


class QdrantVectorStore:
    def __init__(
        self,
        config: Settings = settings,
        *,
        timeout_seconds: float | None = None,
    ) -> None:
        self.config = config
        self.client = QdrantClient(
            url=config.qdrant_url,
            api_key=config.qdrant_api_key or None,
            timeout=timeout_seconds or config.rag_timeout_seconds,
        )

    def ensure_collection(self) -> CollectionProvisionResult:
        created = False
        if not self.client.collection_exists(self.config.qdrant_collection):
            self.client.create_collection(
                collection_name=self.config.qdrant_collection,
                vectors_config={
                    self.config.qdrant_vector_name: models.VectorParams(
                        size=self.config.embedding_dimensions,
                        distance=models.Distance.COSINE,
                    )
                },
            )
            created = True
        else:
            self._validate_collection()
        for field_name, field_schema in FILTER_FIELDS.items():
            self.client.create_payload_index(
                collection_name=self.config.qdrant_collection,
                field_name=field_name,
                field_schema=field_schema,
                wait=True,
            )
        return CollectionProvisionResult(
            collection=self.config.qdrant_collection,
            created=created,
            vector_name=self.config.qdrant_vector_name,
            vector_size=self.config.embedding_dimensions,
            payload_indexes=list(FILTER_FIELDS),
        )

    def _validate_collection(self) -> None:
        info = self.client.get_collection(self.config.qdrant_collection)
        vectors = info.config.params.vectors
        if not isinstance(vectors, dict):
            raise ValueError("Qdrant collection must use named vectors")
        vector = vectors.get(self.config.qdrant_vector_name)
        if vector is None:
            raise ValueError("configured named vector is missing from Qdrant collection")
        if int(vector.size) != self.config.embedding_dimensions:
            raise ValueError("Qdrant vector size does not match EMBEDDING_DIMENSIONS")
        if vector.distance != models.Distance.COSINE:
            raise ValueError("Qdrant collection must use cosine distance")

    def upsert(self, points: list[VectorPoint]) -> int:
        if not points:
            return 0
        for point in points:
            if len(point.vector) != self.config.embedding_dimensions:
                raise ValueError(
                    f"point {point.id} vector dimension does not match "
                    f"{self.config.embedding_dimensions}"
                )
            if point.payload.embedding_model != self.config.embedding_model:
                raise ValueError("point embedding model does not match configuration")
        self.client.upsert(
            collection_name=self.config.qdrant_collection,
            wait=True,
            points=[
                models.PointStruct(
                    id=str(point.id),
                    vector={self.config.qdrant_vector_name: point.vector},
                    payload=point.payload.model_dump(mode="json"),
                )
                for point in points
            ],
        )
        return len(points)

    def delete(self, query_filter: models.Filter) -> None:
        self.client.delete(
            collection_name=self.config.qdrant_collection,
            points_selector=models.FilterSelector(filter=query_filter),
            wait=True,
        )

    def delete_points(self, point_ids: list[str]) -> int:
        if not point_ids:
            return 0
        self.client.delete(
            collection_name=self.config.qdrant_collection,
            points_selector=models.PointIdsList(points=point_ids),
            wait=True,
        )
        return len(point_ids)

    def check_readiness(self) -> tuple[bool, str]:
        try:
            if not self.client.collection_exists(self.config.qdrant_collection):
                return False, "collection_missing"
            self._validate_collection()
            return True, "collection_ready"
        except Exception:
            return False, "connection_failed"

    def close(self) -> None:
        self.client.close()
