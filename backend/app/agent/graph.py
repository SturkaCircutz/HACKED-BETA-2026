"""LangGraph state graph + checkpointer (SQLite in dev, Postgres in prod)."""
import sqlite3
from functools import lru_cache

from langgraph.graph import END, START, StateGraph

from ..config import get_settings
from . import nodes
from .state import ReportState


def build_graph() -> StateGraph:
    g = StateGraph(ReportState)
    for name in ["intake", "geo_resolve", "retrieve_contacts", "nearby_reports", "draft_action",
                 "human_review", "deliver", "track"]:
        g.add_node(name, getattr(nodes, name))
    g.add_edge(START, "intake")
    g.add_edge("intake", "geo_resolve")
    g.add_edge("geo_resolve", "retrieve_contacts")  # 3a and 3b run in parallel
    g.add_edge("geo_resolve", "nearby_reports")
    g.add_edge(["retrieve_contacts", "nearby_reports"], "draft_action")  # join
    g.add_edge("draft_action", "human_review")
    g.add_conditional_edges("human_review", nodes.route_after_review,
                            {"deliver": "deliver", "draft_action": "draft_action", "__end__": END})
    g.add_edge("deliver", "track")
    g.add_edge("track", END)
    return g


def _checkpointer():
    s = get_settings()
    if s.database_url.startswith("postgresql"):
        import psycopg
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row

        url = s.database_url.replace("postgresql+psycopg://", "postgresql://")
        conn = psycopg.Connection.connect(url, autocommit=True, prepare_threshold=0, row_factory=dict_row)
        saver = PostgresSaver(conn)
        saver.setup()
        return saver
    from langgraph.checkpoint.sqlite import SqliteSaver

    return SqliteSaver(sqlite3.connect(s.checkpoint_path, check_same_thread=False))


@lru_cache
def get_graph():
    return build_graph().compile(checkpointer=_checkpointer())
