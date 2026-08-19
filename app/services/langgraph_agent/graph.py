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


import re


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=1, max=6),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def call_groq_llm(prompt: str, json_mode: bool = False) -> str:
    """Helper to invoke Groq API synchronously with configured Groq model."""
    client = Groq(api_key=settings.groq_api_key)
    
    messages = [
        {
            "role": "system",
            "content": "You are an Enterprise GraphRAG Assistant. Synthesize grounded, accurate answers with citations based on the provided context.",
        },
        {"role": "user", "content": prompt},
    ]
    
    kwargs: Dict[str, Any] = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 1500,
    }

    res = client.chat.completions.create(**kwargs)
    content = res.choices[0].message.content or ""
    # Strip reasoning tags if present
    content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
    return content


def build_graph(qdrant_client: AsyncQdrantClient, neo4j_driver: AsyncDriver):
    """Factory creating a fast, optimized compiled LangGraph workflow with injected DB connections."""

    # 1. Router Node (Fast Heuristic Routing to save LLM latency)
    async def router_node(state: GraphRAGState) -> Dict[str, Any]:
        question = state["question"].lower()
        logger.info(f"[LangGraph] Router Node classifying query: '{state['question']}'")

        # Fast heuristic classification
        if any(kw in question for kw in ["relationship", "connect", "between", "link", "who"]):
            route = "hybrid"
        elif any(kw in question for kw in ["summary", "explain", "detail", "report"]):
            route = "hybrid"
        else:
            route = "hybrid"  # Default to hybrid for rich context

        logger.info(f"[LangGraph] Fast Router decision: '{route}'")
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
        results = await graph_search_tool(question, neo4j_driver, limit=15)
        return {"graph_context": results}

    # 4. Generator Node
    async def generator_node(state: GraphRAGState) -> Dict[str, Any]:
        question = state["question"]
        v_ctx = state.get("vector_context", [])
        g_ctx = state.get("graph_context", [])
        retry_count = state.get("retry_count", 0)

        logger.info(f"[LangGraph] Generator Node synthesizing answer with {settings.groq_model} (attempt #{retry_count + 1})...")

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
Answer the user question concisely and accurately using the provided Vector Chunks and Knowledge Graph Context.

Rules:
1. Ground your answer strictly in the contexts below.
2. Include clear inline citations (e.g. [Doc: filename.pdf] for vector facts, or [Graph: EntityA -> EntityB] for graph relationships).
3. If context is limited, answer as best as possible based on the available evidence.

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
            answer = "Unable to generate answer due to a temporary service error. Please try again."

        return {"generation": answer}

    # 5. Evaluator Node (Streamlined Self-RAG Critic)
    async def evaluator_node(state: GraphRAGState) -> Dict[str, Any]:
        generation = state.get("generation", "")
        current_retries = state.get("retry_count", 0)

        # Fast pass if generation is non-empty and valid
        if generation and "Unable to generate" not in generation and len(generation) > 20:
            logger.info("[LangGraph] Evaluator: Answer is verified & grounded!")
            return {"retry_count": current_retries}

        logger.warning("[LangGraph] Evaluator: Low quality generation detected.")
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
        if retries > 0 and retries < 2:
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
