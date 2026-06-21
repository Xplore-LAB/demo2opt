from __future__ import annotations

from typing import Any, Dict

from src.agent.core.runtime import AgentRuntimeHooks
from src.agent.core.state import OptimizationState
from src.agent.workflows.nodes import build_nodes

NODE_SEQUENCE = [
    "bootstrap_run",
    "load_data",
    "confirm_data_range",
    "select_snapshot",
    "semantic_analysis",
    "confirm_overview",
    "extract_features",
    "confirm_candidates",
    "primary_retrieval",
    "confirm_high_risk",
    "reasoning",
    "review_retrieval",
    "decision",
    "generate_report",
    "finalize_success",
    "finalize_error",
]


class _FallbackCompiledGraph:
    def __init__(self, nodes: Dict[str, Any]):
        self.nodes = nodes

    async def ainvoke(self, state: OptimizationState) -> Dict[str, Any]:
        current = "bootstrap_run"
        runtime_state: Dict[str, Any] = dict(state)
        while current and current != "END":
            node = self.nodes[current]
            runtime_state = await node(runtime_state)
            current = str(runtime_state.get("next_node") or "END")
        return runtime_state


def build_optimization_graph(hooks: AgentRuntimeHooks, store: Any):
    nodes = build_nodes(hooks, store)
    try:
        from langgraph.graph import END, START, StateGraph

        def _route_next(state: OptimizationState) -> str:
            return str(state.get("next_node") or "finalize_error")

        graph = StateGraph(OptimizationState)
        for name, func in nodes.items():
            graph.add_node(name, func)
        graph.add_edge(START, "bootstrap_run")
        route_map: Dict[str, Any] = {name: name for name in NODE_SEQUENCE}
        route_map["END"] = END
        for name in NODE_SEQUENCE:
            graph.add_conditional_edges(name, _route_next, route_map)
        return graph.compile()
    except Exception:
        return _FallbackCompiledGraph(nodes)
