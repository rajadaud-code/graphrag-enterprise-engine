import logging
import threading
import uuid
from typing import Any, Dict, List
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384


class EmbeddingModelSingleton:
    _instance: SentenceTransformer | None = None
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> SentenceTransformer:
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    logger.info(f"Loading Hugging Face embedding model '{MODEL_NAME}' into memory...")
                    cls._instance = SentenceTransformer(MODEL_NAME)
                    logger.info("Embedding model loaded successfully.")
        return cls._instance


def generate_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate dense 384-dimensional vector embeddings for a list of text strings."""
    if not texts:
        return []

    model = EmbeddingModelSingleton.get_instance()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return embeddings.tolist()


async def upsert_chunks_to_qdrant(
    qdrant_client: AsyncQdrantClient,
    chunks: List[str],
    filename: str,
    collection_name: str = "documents",
    batch_size: int = 100,
) -> int:
    """Batch embed text chunks and upsert them with payload metadata into Qdrant."""
    if not chunks:
        logger.warning(f"No chunks provided to upsert for file '{filename}'")
        return 0

    # Ensure collection exists
    exists = await qdrant_client.collection_exists(collection_name=collection_name)
    if not exists:
        logger.info(f"Creating Qdrant collection '{collection_name}' with vector size {EMBEDDING_DIMENSION}")
        await qdrant_client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=EMBEDDING_DIMENSION,
                distance=models.Distance.COSINE,
            ),
        )

    # Generate embeddings
    embeddings = generate_embeddings(chunks)

    points: List[models.PointStruct] = []
    for idx, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        chunk_id = str(uuid.uuid4())
        payload: Dict[str, Any] = {
            "chunk_id": chunk_id,
            "text": chunk,
            "filename": filename,
            "chunk_index": idx,
        }
        points.append(
            models.PointStruct(
                id=chunk_id,
                vector=vector,
                payload=payload,
            )
        )

    logger.info(f"Upserting {len(points)} points into Qdrant collection '{collection_name}' in batches of {batch_size}")
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        await qdrant_client.upsert(
            collection_name=collection_name,
            points=batch,
        )

    return len(points)
