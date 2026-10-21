"""LangGraph workflow assembly."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.graph import END, StateGraph

from app.agents.nodes import AnalysisNodes, should_retry_validation
from app.agents.state import AnalysisGraphState
from app.core.config import Settings, get_settings
from app.services.scryfall import ScryfallClient

ProgressCallback = Callable[[str, int], Awaitable[None]]


def build_analysis_graph(
    *,
    scryfall: ScryfallClient,
    llm: BaseChatModel | None,
    settings: Settings | None = None,
    on_progress: ProgressCallback | None = None,
):
    cfg = settings or get_settings()
    nodes = AnalysisNodes(
        scryfall=scryfall,
        llm=llm,
        settings=cfg,
        on_progress=on_progress,
    )

    graph = StateGraph(AnalysisGraphState)
    graph.add_node("fetch_cards", nodes.fetch_cards)
    graph.add_node("calculate_metrics", nodes.calculate_metrics)
    graph.add_node("generate_recommendations", nodes.generate_recommendations)
    graph.add_node("validate_output", nodes.validate_output)
    graph.add_node("persist_result", nodes.persist_result)

    graph.set_entry_point("fetch_cards")
    graph.add_edge("fetch_cards", "calculate_metrics")
    graph.add_edge("calculate_metrics", "generate_recommendations")
    graph.add_edge("generate_recommendations", "validate_output")
    graph.add_conditional_edges(
        "validate_output",
        should_retry_validation,
        {
            "generate_recommendations": "generate_recommendations",
            "persist_result": "persist_result",
        },
    )
    graph.add_edge("persist_result", END)
    return graph.compile()


def create_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """Create the configured LangChain chat model."""
    from langchain_openai import ChatOpenAI

    cfg = settings or get_settings()
    cfg.require_llm_config()
    if cfg.llm_provider.lower() != "openai":
        raise RuntimeError(f"Unsupported LLM_PROVIDER: {cfg.llm_provider}")
    kwargs: dict[str, object] = {
        "model": cfg.llm_model,
        "api_key": cfg.llm_api_key,
        "timeout": cfg.llm_timeout_seconds,
        "max_retries": cfg.llm_max_retries,
    }
    if cfg.llm_base_url:
        kwargs["base_url"] = cfg.llm_base_url
    return ChatOpenAI(**kwargs)
