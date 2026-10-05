from __future__ import annotations

import argparse
import json

from app.core.config import settings
from app.vector_store.qdrant import QdrantVectorStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the configured Qdrant collection")
    parser.add_argument("action", choices=("status", "ensure-collection"))
    args = parser.parse_args()

    store = QdrantVectorStore(settings)
    try:
        if args.action == "ensure-collection":
            result = store.ensure_collection().model_dump(mode="json")
        else:
            ok, detail = store.check_readiness()
            result = {
                "ready": ok,
                "detail": detail,
                "collection": settings.qdrant_collection,
                "vector_name": settings.qdrant_vector_name,
                "vector_size": settings.embedding_dimensions,
            }
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
