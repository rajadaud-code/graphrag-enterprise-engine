import logging
from typing import Any, Dict, List
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient

from app.services.embedding_service import generate_embeddings
from app.services.graph_extractor import extract_entities_with_groq

logger = logging.getLogger(__name__)


async def vector_search_tool(
    question: str,
    qdrant_client: AsyncQdrantClient,
    collection_name: str = "documents",
    limit: int = 3,
) -> List[Dict[str, Any]]:
    """Retrieve top 3 semantically similar vector chunks from Qdrant."""
    logger.info(f"Executing Vector Search tool for query: '{question}'")

    try:
        exists = await qdrant_client.collection_exists(collection_name)
        if not exists:
            logger.warning(f"Collection '{collection_name}' does not exist in Qdrant")
            return []

        query_vectors = generate_embeddings([question])
        if not query_vectors:
            return []

        query_vector = query_vectors[0]
        
        # Support both qdrant-client query_points API (v1.10+) and search API
        if hasattr(qdrant_client, "query_points"):
            response = await qdrant_client.query_points(
                collection_name=collection_name,
                query=query_vector,
                limit=limit,
            )
            search_res = response.points
        else:
            search_res = await qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
            )

        results: List[Dict[str, Any]] = []
        for hit in search_res:
            payload = hit.payload or {}
            results.append(
                {
                    "score": float(hit.score) if hasattr(hit, "score") else 1.0,
                    "chunk_id": payload.get("chunk_id", str(hit.id)),
                    "text": payload.get("text", ""),
                    "filename": payload.get("filename", "unknown"),
                    "type": "vector",
                }
            )

        logger.info(f"Vector search retrieved {len(results)} chunks from Qdrant")
        return results
    except Exception as exc:
        logger.error(f"Error executing vector search tool: {exc}")
        return []


async def graph_search_tool(
    question: str,
    neo4j_driver: AsyncDriver,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """Extract entities from user query and execute 2-hop Cypher relationship query in Neo4j."""
    logger.info(f"Executing Graph Search tool for query: '{question}'")

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
            logger.info("No query entities found for Graph Search")
            return []

        # Step 2: 2-hop Cypher Graph Traversal
        cypher_query = """
        UNWIND $entity_names AS search_name
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower(search_name) OR toLower(search_name) CONTAINS toLower(e.name)
        MATCH (e)-[r:RELATES_TO*1..2]-(target:Entity)
        RETURN DISTINCT e.name AS source,
               e.type AS source_type,
               [rel IN r | rel.type] AS relation_types,
               target.name AS target,
               target.type AS target_type
        LIMIT $limit
        """

        results: List[Dict[str, Any]] = []
        async with neo4j_driver.session() as session:
            res = await session.run(cypher_query, entity_names=entity_names, limit=limit)
            async for record in res:
                results.append(
                    {
                        "source": record["source"],
                        "source_type": record["source_type"],
                        "relations": record["relation_types"],
                        "target": record["target"],
                        "target_type": record["target_type"],
                        "type": "graph",
                    }
                )

        logger.info(f"Graph search retrieved {len(results)} multi-hop relationships from Neo4j")
        return results
    except Exception as exc:
        logger.error(f"Error executing graph search tool: {exc}")
        return []
