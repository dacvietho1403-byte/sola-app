"""Luồng vận hành (O&M): AI-08 giám sát sản lượng -> AI-09 sự cố & SLA khi bất thường."""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph

from .config import SETTINGS as S
from .state import log, new_id


class OMState(TypedDict, total=False):
    project: dict
    period: str
    monthly_kwh: float
    days: int
    production: dict
    incident: dict
    audit_logs: Annotated[list[dict], operator.add]


def monitor_node(state: OMState) -> dict:
    p = state["project"]
    days = state.get("days") or 30
    expected = p["capacity_kwp"] * S.specific_yield / 365 * days
    ratio = state["monthly_kwh"] / expected if expected else 0
    record = {
        "project_id": p["project_id"],
        "period": state.get("period"),
        "actual_kwh": state["monthly_kwh"],
        "expected_kwh": round(expected),
        "performance_ratio": round(ratio, 3),
        "status": "NORMAL" if ratio >= S.performance_threshold else "ANOMALY",
    }
    return {"production": record,
            "audit_logs": [log("AI-08 Giám sát sản lượng", "Đối chiếu sản lượng thực tế với kỳ vọng", record)]}


def incident_node(state: OMState) -> dict:
    prod = state["production"]
    critical = prod["performance_ratio"] < 0.6
    incident = {
        "incident_id": new_id("INC"),
        "project_id": prod["project_id"],
        "issue": f"Sản lượng {prod['performance_ratio']:.0%} so với kỳ vọng (kỳ {prod['period']})",
        "severity": "CRITICAL" if critical else "MAJOR",
        "assigned_vendor": S.om_vendor,
        "sla_hours": S.sla_hours_critical if critical else S.sla_hours_normal,
        "status": "OPEN",
    }
    return {"incident": incident,
            "audit_logs": [log("AI-09 Sự cố & SLA", "Mở ticket sự cố và điều phối bảo trì", incident)]}


def build_om_graph():
    g = StateGraph(OMState)
    g.add_node("monitor", monitor_node)
    g.add_node("incident", incident_node)
    g.add_edge(START, "monitor")
    g.add_conditional_edges("monitor",
                            lambda s: "incident" if s["production"]["status"] == "ANOMALY" else END,
                            ["incident", END])
    g.add_edge("incident", END)
    return g.compile()
