import operator
from typing import Annotated, Any, Dict, List, TypedDict


class GraphRAGState(TypedDict):
    """LangGraph state representation for stateful hybrid retrieval and reasoning."""

    question: str
    route_decision: str
    vector_context: Annotated[List[Dict[str, Any]], operator.add]
    graph_context: Annotated[List[Dict[str, Any]], operator.add]
    generation: str
    retry_count: int
