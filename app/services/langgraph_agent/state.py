import operator
from typing import Annotated, Any, Dict, List, TypedDict


class GraphRAGState(TypedDict):
    """LangGraph state representation for stateful multi-tenant hybrid retrieval and reasoning."""

    tenant_id: str
    session_id: str
    question: str
    route_decision: str
    vector_context: Annotated[List[Dict[str, Any]], operator.add]
    graph_context: Annotated[List[Dict[str, Any]], operator.add]
    generation: str
    retry_count: int
    chat_history: Annotated[List[Dict[str, str]], operator.add]
