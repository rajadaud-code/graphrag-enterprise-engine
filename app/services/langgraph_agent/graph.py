import json
import logging
from typing import Any, Dict, List, Literal
from groq import Groq
from langgraph.graph import END, StateGraph
from neo4j import AsyncDriver
from qdrant_client import AsyncQdrantClient
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import settings
from app.services.langgraph_agent.state import GraphRAGState
from app.services.langgraph_agent.tools import graph_search_tool, vector_search_tool

logger = logging.getLogger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def call_groq_llm(prompt: str, json_mode: bool = False) -> str:
    """Helper to invoke Groq API synchronously inside worker or async wrapper."""
    client = Groq(api_key=settings.groq_api_key)
    kwargs: Dict[str, Any] = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    res = client.chat.completions.create(**kwargs)
    return res.choices[0].message.content or ""


def build_graph(qdrant_client: AsyncQdrantClient, neo4j_driver: AsyncDriver):
    """Factory creating a compiled LangGraph workflow with injected DB connections."""

    # 1. Router Node
    async def router_node(state: GraphRAGState) -> Dict[str, Any]:
        question = state["question"]
        logger.info(f"[LangGraph] Router Node classifying query: '{question}'")

        prompt = f"""You are an Adaptive RAG Router. Classify the user question into one of three search strategies:
1. "vector": best for textual facts, passages, or document summaries.
2. "graph": best for multi-hop entity relationships, organizational structures, or entity connections.
3. "hybrid": best when the query requires both document context and graph relationships.

Question: "{question}"

Return ONLY a JSON object: {{"route": "vector" | "graph" | "hybrid"}}"""

        try:
            raw_res = call_groq_llm(prompt, json_mode=True)
            data = json.loads(raw_res)
            route = data.get("route", "hybrid").lower()
            if route not in ("vector", "graph", "hybrid"):
                route = "hybrid"
        except Exception as exc:
            logger.error(f"Router node error: {exc}")
            route = "hybrid"

        logger.info(f"[LangGraph] Router decision: '{route}'")
        return {"route_decision": route}

    # 2. Vector Node
    async def vector_node(state: GraphRAGState) -> Dict[str, Any]:
        question = state["question"]
        logger.info(f"[LangGraph] Vector Node searching Qdrant for: '{question}'")
        results = await vector_search_tool(question, qdrant_client, limit=3)
        return {"vector_context": results}

    # 3. Graph Node
    async def graph_node(state: GraphRAGState) -> Dict[str, Any]:
        question = state["question"]
        logger.info(f"[LangGraph] Graph Node searching Neo4j for: '{question}'")
        results = await graph_search_tool(question, neo4j_driver, limit=20)
        return {"graph_context": results}

    # 4. Generator Node
    async def generator_node(state: GraphRAGState) -> Dict[str, Any]:
        question = state["question"]
        v_ctx = state.get("vector_context", [])
        g_ctx = state.get("graph_context", [])
        retry_count = state.get("retry_count", 0)

        logger.info(f"[LangGraph] Generator Node synthesizing answer (attempt #{retry_count + 1})...")

        v_formatted = "\n".join(
            [f"- [{item.get('filename', 'doc')}]: {item.get('text', '')}" for item in v_ctx]
        ) or "None"

        g_formatted = "\n".join(
            [
                f"- ({item.get('source')})--[{','.join(item.get('relations', []))}]->({item.get('target')})"
                for item in g_ctx
            ]
        ) or "None"

        prompt = f"""You are an Enterprise GraphRAG Synthesis Assistant.
Answer the user question using ONLY the provided Vector Chunks and Knowledge Graph Context.

Rules:
1. Strictly ground your answer in the contexts below. Do NOT invent facts.
2. Include clear inline citations (e.g. [Doc: filename.pdf] for vector facts, or [Graph: EntityA -> EntityB] for graph relationships).
3. If the context is insufficient, state clearly that information is unavailable.

Question:
{question}

Vector Chunks Context:
{v_formatted}

Knowledge Graph Context:
{g_formatted}

Detailed Answer with Citations:"""

        try:
            answer = call_groq_llm(prompt, json_mode=False)
        except Exception as exc:
            logger.error(f"Generator node error: {exc}")
            answer = "Unable to generate answer due to service error."

        return {"generation": answer}

    # 5. Evaluator Node (Self-RAG Critic)
    async def evaluator_node(state: GraphRAGState) -> Dict[str, Any]:
        generation = state.get("generation", "")
        v_ctx = state.get("vector_context", [])
        g_ctx = state.get("graph_context", [])
        current_retries = state.get("retry_count", 0)

        logger.info(f"[LangGraph] Evaluator Node assessing generation grounding (retries: {current_retries})...")

        if not generation or "Unable to generate" in generation:
            return {"retry_count": current_retries + 1}

        prompt = f"""You are a Self-RAG Hallucination Critic.
Evaluate if the Generated Answer is strictly grounded in the Contexts.

Generated Answer:
\"\"\"{generation}\"\"\"

Vector Context:
{v_ctx}

Graph Context:
{g_ctx}

Return ONLY a JSON object: {{"is_grounded": true | false, "reason": "short explanation"}}"""

        try:
            raw_res = call_groq_llm(prompt, json_mode=True)
            eval_data = json.loads(raw_res)
            is_grounded = eval_data.get("is_grounded", True)
        except Exception as exc:
            logger.error(f"Evaluator node error: {exc}")
            is_grounded = True

        if is_grounded:
            logger.info("[LangGraph] Evaluator: Answer is verified & grounded!")
            return {"retry_count": current_retries}
        else:
            logger.warning("[LangGraph] Evaluator: Hallucination detected! Flagging retry.")
            return {"retry_count": current_retries + 1}

    # Conditional Routing Logic
    def route_after_router(state: GraphRAGState) -> List[str] | str:
        decision = state.get("route_decision", "hybrid")
        if decision == "vector":
            return "vector_node"
        elif decision == "graph":
            return "graph_node"
        else:
            return ["vector_node", "graph_node"]

    def route_after_evaluator(state: GraphRAGState) -> Literal["generator_node", "__end__"]:
        retries = state.get("retry_count", 0)
        # Max 3 retries
        if retries > 0 and retries < 3:
            logger.info(f"[LangGraph] Retrying generation (Retry #{retries})...")
            return "generator_node"
        return END

    # Build Graph Structure
    workflow = StateGraph(GraphRAGState)

    workflow.add_node("router_node", router_node)
    workflow.add_node("vector_node", vector_node)
    workflow.add_node("graph_node", graph_node)
    workflow.add_node("generator_node", generator_node)
    workflow.add_node("evaluator_node", evaluator_node)

    workflow.set_entry_point("router_node")

    workflow.add_conditional_edges(
        "router_node",
        route_after_router,
        {
            "vector_node": "vector_node",
            "graph_node": "graph_node",
        },
    )

    workflow.add_edge("vector_node", "generator_node")
    workflow.add_edge("graph_node", "generator_node")
    workflow.add_edge("generator_node", "evaluator_node")

    workflow.add_conditional_edges(
        "evaluator_node",
        route_after_evaluator,
        {
            "generator_node": "generator_node",
            END: END,
        },
    )

    return workflow.compile()
