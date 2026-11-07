"""Lắp ráp luồng chính thành StateGraph của LangGraph."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from . import nodes as n
from .state import PipelineState


def _stopped_or(next_node: str):
    def route(state: PipelineState) -> str:
        return END if state.get("stage") == "STOPPED" else next_node
    return route


def route_after_quote(state: PipelineState) -> str:
    stage = state.get("stage")
    if stage == "QUOTE_APPROVED":
        return "contract"
    if stage == "QUOTE_REVISION":
        return "quotation"
    return END


def route_after_acceptance(state: PipelineState) -> str:
    stage = state.get("stage")
    if stage == "ACCEPTED":
        return "invoice_acceptance"
    if stage == "REWORK_REQUIRED":
        return "construction"
    return END


def _approval_node(fn):
    """Bọc node duyệt: quyết định hợp lệ thì xóa cờ hỏi lại."""
    def wrapped(state: PipelineState) -> dict:
        out = fn(state)
        out.setdefault("approval_retry", None)
        return out
    wrapped.__name__ = fn.__name__
    return wrapped


# Node duyệt -> mã bước duyệt (khóa trong approval.APPROVAL_RIGHTS)
APPROVAL_NODES = {"survey_result": "survey", "approve_quote": "quote", "sign_contract": "contract",
                  "acceptance": "acceptance", "approve_finance": "finance"}


def _with_retry(node: str, route):
    """Quyết định không hợp lệ thì quay lại chính bước duyệt, ngược lại đi theo route."""
    step = APPROVAL_NODES[node]

    def wrapped(state: PipelineState) -> str:
        return node if state.get("approval_retry") == step else route(state)
    return wrapped


def build_graph(checkpointer: BaseCheckpointSaver | None = None):
    g = StateGraph(PipelineState)
    g.add_node("marketing", n.marketing_node)                # AI-03
    g.add_node("lead_filter", n.lead_filter_node)            # AI-04
    g.add_node("survey_request", n.survey_request_node)      # AI-05
    g.add_node("survey_result", _approval_node(n.survey_result_node))        # Duyệt: TP QLKT
    g.add_node("quotation", n.quotation_node)                # AI-06
    g.add_node("approve_quote", _approval_node(n.approve_quote_node))        # Duyệt: TP Thị trường
    g.add_node("contract", n.contract_node)                  # AI-13
    g.add_node("sign_contract", _approval_node(n.sign_contract_node))        # Duyệt: Giám đốc
    g.add_node("invoice_advance", n.invoice_advance_node)    # AI-11
    g.add_node("construction", n.construction_node)          # AI-07
    g.add_node("acceptance", _approval_node(n.acceptance_node))              # Duyệt: TP QLKT
    g.add_node("invoice_acceptance", n.invoice_acceptance_node)  # AI-11
    g.add_node("finance", n.finance_node)                    # AI-10
    g.add_node("approve_finance", _approval_node(n.approve_finance_node))    # Duyệt: Kế toán trưởng
    g.add_node("investment", n.investment_node)              # AI-02
    g.add_node("executive_report", n.executive_report_node)  # AI-01

    g.add_edge(START, "marketing")
    g.add_edge("marketing", "lead_filter")
    g.add_conditional_edges("lead_filter", _stopped_or("survey_request"), ["survey_request", END])
    g.add_edge("survey_request", "survey_result")
    g.add_conditional_edges("survey_result", _with_retry("survey_result", _stopped_or("quotation")),
                            ["survey_result", "quotation", END])
    g.add_edge("quotation", "approve_quote")
    g.add_conditional_edges("approve_quote", _with_retry("approve_quote", route_after_quote),
                            ["approve_quote", "contract", "quotation", END])
    g.add_edge("contract", "sign_contract")
    g.add_conditional_edges("sign_contract", _with_retry("sign_contract", _stopped_or("invoice_advance")),
                            ["sign_contract", "invoice_advance", END])
    g.add_edge("invoice_advance", "construction")
    g.add_edge("construction", "acceptance")
    g.add_conditional_edges("acceptance", _with_retry("acceptance", route_after_acceptance),
                            ["acceptance", "invoice_acceptance", "construction", END])
    g.add_edge("invoice_acceptance", "finance")
    g.add_edge("finance", "approve_finance")
    g.add_conditional_edges("approve_finance", _with_retry("approve_finance", _stopped_or("investment")),
                            ["approve_finance", "investment", END])
    g.add_edge("investment", "executive_report")
    g.add_edge("executive_report", END)
    return g.compile(checkpointer=checkpointer or InMemorySaver())


def sqlite_checkpointer(db_path: str | Path):
    """Checkpointer lưu trạng thái ra file SQLite: tắt chương trình vẫn duyệt tiếp được."""
    from langgraph.checkpoint.sqlite import SqliteSaver

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn)


def pending_approval(graph, thread_id: str) -> dict | None:
    """Trả về yêu cầu duyệt đang chờ của một hồ sơ (thread), hoặc None."""
    snap = graph.get_state({"configurable": {"thread_id": thread_id}})
    return snap.interrupts[0].value if snap.interrupts else None
