import json
import logging
from typing import Any, Dict, List
from groq import Groq
from neo4j import AsyncDriver
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are an expert Enterprise Knowledge Graph Extractor.
Extract key domain entities and their semantic relationships from the provided text chunk.

Return ONLY a JSON object matching this exact schema:
{{
  "entities": [
    {{
      "name": "Exact Name of Entity",
      "type": "ORGANIZATION | PERSON | LOCATION | CONCEPT | PRODUCT | EVENT | OTHER",
      "description": "Brief description of entity"
    }}
  ],
  "relationships": [
    {{
      "source": "Source Entity Name",
      "target": "Target Entity Name",
      "type": "UPPERCASE_RELATION_TYPE",
      "description": "Brief description of relationship"
    }}
  ]
}}

Text Chunk to Process:
\"\"\"{chunk_text}\"\"\"
"""


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(min=2, max=30),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def extract_entities_with_groq(chunk_text: str) -> Dict[str, Any]:
    """Call Groq LLM using llama-3.3-70b-versatile with strict JSON mode and tenacity retry backoff."""
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is not configured in settings")

    client = Groq(api_key=settings.groq_api_key)
    prompt = EXTRACTION_PROMPT.format(chunk_text=chunk_text)

    logger.info("Calling Groq LLM (llama-3.3-70b-versatile) for JSON entity extraction...")
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.1,
    )

    content = (response.choices[0].message.content or "{}").strip()
    if content.startswith("```json"):
        content = content.replace("```json", "", 1).rstrip("```").strip()
    elif content.startswith("```"):
        content = content.replace("```", "", 1).rstrip("```").strip()

    try:
        extracted = json.loads(content)
        if isinstance(extracted, str):
            extracted = json.loads(extracted)
    except Exception as exc:
        logger.error(f"Failed to parse LLM JSON content: {exc}")
        extracted = {}

    if not isinstance(extracted, dict):
        extracted = {}

    entities = extracted.get("entities", [])
    relationships = extracted.get("relationships", [])

    if not isinstance(entities, list):
        entities = []
    if not isinstance(relationships, list):
        relationships = []

    return {
        "entities": entities,
        "relationships": relationships,
    }


async def ingest_graph_to_neo4j(
    neo4j_driver: AsyncDriver,
    chunk_id: str,
    filename: str,
    chunk_text: str,
    graph_data: Dict[str, Any],
) -> Dict[str, int]:
    """Ingest extracted entities, chunk node, and relationships into Neo4j using Cypher MERGE."""
    entities: List[Dict[str, Any]] = graph_data.get("entities", [])
    relationships: List[Dict[str, Any]] = graph_data.get("relationships", [])

    if not isinstance(entities, list):
        entities = []
    if not isinstance(relationships, list):
        relationships = []

    cypher_chunk_and_entities = """
    MERGE (c:Chunk {id: $chunk_id})
    ON CREATE SET c.filename = $filename, c.text = $chunk_text

    WITH c
    UNWIND $entities AS entity
    MERGE (e:Entity {name: entity.name})
    ON CREATE SET e.type = entity.type, e.description = entity.description

    MERGE (c)-[:HAS_ENTITY]->(e)
    MERGE (e)-[:MENTIONED_IN]->(c)
    """

    cypher_relationships = """
    UNWIND $relationships AS rel
    MERGE (src:Entity {name: rel.source})
    MERGE (tgt:Entity {name: rel.target})
    MERGE (src)-[r:RELATES_TO {type: coalesce(rel.type, 'RELATED')}]->(tgt)
    ON CREATE SET r.description = rel.description
    """

    async with neo4j_driver.session() as session:
        # Ingest Chunk & Entities
        if entities:
            await session.run(
                cypher_chunk_and_entities,
                chunk_id=chunk_id,
                filename=filename,
                chunk_text=chunk_text,
                entities=entities,
            )

        # Ingest Entity-to-Entity Relationships
        if relationships:
            await session.run(
                cypher_relationships,
                relationships=relationships,
            )

    logger.info(
        f"Ingested Graph for Chunk {chunk_id}: {len(entities)} entities, {len(relationships)} relationships into Neo4j"
    )
    return {
        "entities_count": len(entities),
        "relationships_count": len(relationships),
    }
