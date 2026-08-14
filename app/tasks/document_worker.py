import asyncio
import logging
import os
import uuid
from typing import Any, Dict, List

from neo4j import AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient

from app.core.config import settings
from app.db.neo4j_client import get_sanitized_neo4j_uri
from app.services.embedding_service import upsert_chunks_to_qdrant
from app.services.graph_extractor import extract_entities_with_groq, ingest_graph_to_neo4j
from app.tasks.celery_app import celery_app
from app.utils.text_processing import extract_text_from_pdf, split_text_into_chunks

logger = logging.getLogger(__name__)

MAX_GRAPH_CHUNKS_PER_DOC = 30  # Cap graph extraction to 30 chunks per document to respect LLM rate limits


async def run_async_document_pipeline(file_path: str, filename: str) -> Dict[str, Any]:
    """Execute complete ingestion pipeline: extraction, chunking, Qdrant vectorization, and Neo4j graph extraction."""
    logger.info(f"Extracting text from PDF file '{filename}' ({file_path})...")
    text = extract_text_from_pdf(file_path)
    chunks = split_text_into_chunks(text, chunk_size=1000, chunk_overlap=200)

    if not chunks:
        logger.warning(f"No text extracted from document '{filename}'")
        return {"filename": filename, "status": "empty", "chunks_count": 0}

    logger.info(f"Document '{filename}' split into {len(chunks)} total text chunks.")

    # Step A: Embed and Upsert Chunks into Qdrant (Batched)
    qdrant_client = AsyncQdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )
    try:
        points_inserted = await upsert_chunks_to_qdrant(
            qdrant_client=qdrant_client,
            chunks=chunks,
            filename=filename,
            batch_size=100,
        )
        logger.info(f"Successfully stored {points_inserted} vector points in Qdrant for '{filename}'")
    finally:
        await qdrant_client.close()

    # Step B: LLM Entity Extraction and Neo4j Knowledge Graph Ingestion
    neo4j_uri = get_sanitized_neo4j_uri(settings.neo4j_uri)
    neo4j_driver = AsyncGraphDatabase.driver(
        neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )
    total_entities = 0
    total_relationships = 0

    # Sample chunks if document is large to respect LLM rate limits
    if len(chunks) > MAX_GRAPH_CHUNKS_PER_DOC:
        stride = len(chunks) // MAX_GRAPH_CHUNKS_PER_DOC
        graph_target_chunks = chunks[::stride][:MAX_GRAPH_CHUNKS_PER_DOC]
        logger.info(f"Sampled {len(graph_target_chunks)} representative chunks from {len(chunks)} for Graph Extraction.")
    else:
        graph_target_chunks = chunks

    try:
        for idx, chunk in enumerate(graph_target_chunks):
            chunk_id = f"{filename}_chunk_{idx}_{uuid.uuid4().hex[:6]}"
            try:
                graph_data = extract_entities_with_groq(chunk)
                res = await ingest_graph_to_neo4j(
                    neo4j_driver=neo4j_driver,
                    chunk_id=chunk_id,
                    filename=filename,
                    chunk_text=chunk,
                    graph_data=graph_data,
                )
                total_entities += res["entities_count"]
                total_relationships += res["relationships_count"]
            except Exception as exc:
                logger.error(f"Failed graph extraction on chunk {idx+1}/{len(graph_target_chunks)} of '{filename}': {exc}")
    finally:
        await neo4j_driver.close()

    logger.info(
        f"Pipeline complete for '{filename}': {points_inserted} vectors in Qdrant, "
        f"{total_entities} entities and {total_relationships} relationships in Neo4j."
    )

    return {
        "filename": filename,
        "status": "success",
        "chunks_count": len(chunks),
        "qdrant_vectors_inserted": points_inserted,
        "neo4j_entities_count": total_entities,
        "neo4j_relationships_count": total_relationships,
    }


@celery_app.task(name="process_document")
def process_document_task(file_path: str, filename: str) -> Dict[str, Any]:
    """Celery worker task handling full document pipeline and disk cleanup."""
    logger.info(f"Starting background processing task for: {filename} ({file_path})")

    try:
        result = asyncio.run(run_async_document_pipeline(file_path, filename))
        return result
    except Exception as exc:
        logger.error(f"Critical error in document processing task for '{filename}': {exc}", exc_info=True)
        raise exc
    finally:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Cleaned up temporary file: {file_path}")
            except Exception as remove_err:
                logger.error(f"Failed to delete temporary file {file_path}: {remove_err}")
