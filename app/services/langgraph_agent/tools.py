import logging
from typing import Any, Dict, List
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models

from app.services.embedding_service import generate_embeddings
from app.services.graph_extractor import extract_entities_with_groq

logger = logging.getLogger(__name__)


async def vector_search_tool(
    question: str,
    qdrant_client: AsyncQdrantClient,
    tenant_id: str = "default_tenant",
    collection_name: str = "documents",
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Retrieve top semantically similar vector chunks from Qdrant strictly filtered by tenant_id."""
    logger.info(f"Executing Vector Search tool for Tenant '{tenant_id}', query: '{question}'")

    try:
        exists = await qdrant_client.collection_exists(collection_name)
        if not exists:
            logger.warning(f"Collection '{collection_name}' does not exist in Qdrant")
            return []

        query_vectors = generate_embeddings([question])
        if not query_vectors:
            return []

        query_vector = query_vectors[0]

        # Multi-Tenant Payload Filter
        tenant_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="tenant_id",
                    match=models.MatchValue(value=tenant_id),
                )
            ]
        )

        # Support both qdrant-client query_points API (v1.10+) and search API
        if hasattr(qdrant_client, "query_points"):
            response = await qdrant_client.query_points(
                collection_name=collection_name,
                query=query_vector,
                query_filter=tenant_filter,
                limit=limit,
            )
            search_res = response.points
        else:
            search_res = await qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                query_filter=tenant_filter,
                limit=limit,
            )

        results: List[Dict[str, Any]] = []
        for hit in search_res:
            payload = hit.payload or {}
            results.append(
                {
                    "score": float(hit.score) if hasattr(hit, "score") else 1.0,
                    "chunk_id": payload.get("chunk_id", str(hit.id)),
                    "tenant_id": payload.get("tenant_id", tenant_id),
                    "text": payload.get("text", ""),
                    "filename": payload.get("filename", "unknown"),
                    "type": "vector",
                }
            )

        logger.info(f"Vector search retrieved {len(results)} chunks from Qdrant for Tenant '{tenant_id}'")
        return results
    except Exception as exc:
        logger.error(f"Error executing vector search tool for tenant '{tenant_id}': {exc}")
        return []


async def graph_search_tool(
    question: str,
    neo4j_driver: AsyncDriver,
    tenant_id: str = "default_tenant",
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Extract entities from user query and execute 2-hop Cypher traversal in Neo4j filtered by tenant_id."""
    logger.info(f"Executing Graph Search tool for Tenant '{tenant_id}', query: '{question}'")

    try:
        # Step 1: LLM Entity Extraction on query
        entity_names: List[str] = []
        try:
            extraction = extract_entities_with_groq(question)
            entity_names = [
                e.get("name") for e in extraction.get("entities", []) if e.get("name")
            ]
        except Exception as exc:
            logger.warning(f"LLM entity extraction failed on query: {exc}")

        if not entity_names:
            entity_names = [
                word.strip()
                for word in question.split()
                if len(word) > 3 and word.isalnum()
            ]

        if not entity_names:
            logger.info(f"No query entities found for Graph Search (Tenant: '{tenant_id}')")
            return []

        # Step 2: 2-hop Cypher Graph Traversal strictly partitioned by tenant_id
        cypher_query = """
        UNWIND $entity_names AS search_name
        MATCH (e:Entity {tenant_id: $tenant_id})
        WHERE toLower(e.name) CONTAINS toLower(search_name) OR toLower(search_name) CONTAINS toLower(e.name)
        MATCH (e)-[r:RELATES_TO*1..2]-(target:Entity {tenant_id: $tenant_id})
        WHERE all(rel in r WHERE rel.tenant_id = $tenant_id)
        RETURN DISTINCT e.name AS source,
               e.type AS source_type,
               [rel IN r | rel.type] AS relation_types,
               target.name AS target,
               target.type AS target_type
        LIMIT $limit
        """

        results: List[Dict[str, Any]] = []
        async with neo4j_driver.session() as session:
            res = await session.run(
                cypher_query,
                entity_names=entity_names,
                tenant_id=tenant_id,
                limit=limit,
            )
            async for record in res:
                results.append(
                    {
                        "source": record["source"],
                        "source_type": record["source_type"],
                        "relations": record["relation_types"],
                        "target": record["target"],
                        "target_type": record["target_type"],
                        "tenant_id": tenant_id,
                        "type": "graph",
                    }
                )

        logger.info(
            f"Graph search retrieved {len(results)} multi-hop relationships from Neo4j for Tenant '{tenant_id}'"
        )
        return results
    except Exception as exc:
        logger.error(f"Error executing graph search tool for tenant '{tenant_id}': {exc}")
        return []
