import pytest
from langgraph.types import Command

from agents.cli import DEMO_LEAD, main as cli_main
from agents.config import SETTINGS
from agents.graph import build_graph, pending_approval, sqlite_checkpointer
from agents.nodes import invoice_acceptance_node, contract_node
from agents.om import build_om_graph
from agents.state import GateError

TECH = {"role": "TECH_HEAD", "user": "TP QLKT", "approved": True, "capacity_kwp": 160}
MKT = {"role": "MARKETING_HEAD", "user": "TP TT", "approved": True}
DIR = {"role": "DIRECTOR", "user": "GĐ", "approved": True}
ACC = {"role": "TECH_HEAD", "user": "TP QLKT", "approved": True}
FIN = {"role": "CHIEF_ACCOUNTANT", "user": "KTT", "approved": True}


def cfg(t="T1"):
    return {"configurable": {"thread_id": t}}


def start(lead=None, thread="T1", graph=None):
    graph = graph or build_graph()
    graph.invoke({"raw_lead": lead or DEMO_LEAD}, cfg(thread))
    return graph


def resume(graph, decision, thread="T1"):
    graph.invoke(Command(resume=decision), cfg(thread))
    return graph.get_state(cfg(thread)).values


def test_full_pipeline_happy_path():
    g = start()
    steps = []
    for d in (TECH, MKT, DIR, ACC, FIN):
        steps.append(pending_approval(g, "T1")["step"])
        s = resume(g, d)
    assert steps == ["survey", "quote", "contract", "acceptance", "finance"]
    assert s["stage"] == "COMPLETED"
    assert s["contract"]["status"] == "SIGNED" and s["contract"]["signed_by"] == "GĐ"
    # 3 đợt thanh toán cộng đúng 100% giá trị hợp đồng trước VAT
    assert sum(i["amount_before_vat"] for i in s["invoices"]) == s["contract"]["value_before_vat"]
    assert [i["milestone"] for i in s["invoices"]] == ["advance", "acceptance", "retention"]
    assert s["invoices"][-1]["status"] == "SCHEDULED"
    assert s["report"]["human_decisions"] == 5
    assert 0 < s["investment"]["irr"] < 1


def test_quote_price_calculation():
    g = start()
    s = resume(g, TECH)
    q = s["quotation"]
    assert q["estimated_cost"] == 160 * SETTINGS.unit_cost_per_kwp
    assert q["price_before_vat"] == round(q["estimated_cost"] * (1 + SETTINGS.target_margin))
    assert q["total_price"] == q["price_before_vat"] + q["vat"]


def test_unqualified_lead_stops():
    s = start({**DEMO_LEAD, "budget": 100_000_000, "monthly_bill": 3_000_000,
               "owns_roof": False, "roof_area_m2": 80}).get_state(cfg()).values
    assert s["stage"] == "STOPPED" and s["lead"]["status"] == "UNQUALIFIED"
    assert "survey" not in s


def test_incomplete_lead_stops_without_crash():
    s = start({"id": "L-9", "name": "Thiếu dữ liệu"}).get_state(cfg()).values
    assert s["stage"] == "STOPPED" and "budget" in s["stop_reason"]


@pytest.mark.parametrize("bad", [
    {"role": "AGENT_AI", "user": "AI-01", "approved": True},
    {"role": "MARKETING_HEAD", "user": "TP TT", "approved": True},
    {"role": "TECH_HEAD", "user": "", "approved": True},
    {"role": "KHONG_CO", "user": "X", "approved": True},
])
def test_wrong_role_is_refused_and_asked_again(bad):
    g = start()
    s = resume(g, bad)
    assert pending_approval(g, "T1")["step"] == "survey"
    assert s["stage"] == "SURVEY_SCHEDULED"
    assert s["audit_logs"][-1]["agent"] == "HỆ THỐNG"
    s = resume(g, TECH)
    assert s["survey"]["status"] == "COMPLETED"


def test_quote_revision_then_reject():
    g = start()
    resume(g, TECH)
    s = resume(g, {**MKT, "approved": False, "revise_margin": 0.12})
    assert s["quotation"]["revision"] == 2 and s["quotation"]["margin"] == 0.12
    assert pending_approval(g, "T1")["step"] == "quote"
    s = resume(g, {**MKT, "approved": False})
    assert s["stage"] == "STOPPED" and s["quotation"]["status"] == "REJECTED"
    assert "contract" not in s


def test_director_refuses_contract_no_invoice():
    g = start()
    for d in (TECH, MKT):
        resume(g, d)
    s = resume(g, {**DIR, "approved": False})
    assert s["contract"]["status"] == "CANCELLED"
    assert not s.get("invoices")


def test_acceptance_rework_loop_and_limit():
    g = start()
    for d in (TECH, MKT, DIR):
        resume(g, d)
    fail = {**ACC, "approved": False, "defects": ["Thiếu tiếp địa"]}
    s = resume(g, fail)
    assert s["project"]["rework_count"] == 1 and pending_approval(g, "T1")["step"] == "acceptance"
    resume(g, fail)
    s = resume(g, fail)
    assert s["stage"] == "STOPPED"
    assert [i["milestone"] for i in s["invoices"]] == ["advance"]


def test_over_budget_warning():
    g = start({**DEMO_LEAD, "budget": 1_800_000_000})
    s = resume(g, TECH)
    assert any("Vượt ngân sách" in w for w in s["quotation"]["warnings"])


def test_missing_tax_code_blocks_invoice_issue():
    lead = {k: v for k, v in DEMO_LEAD.items() if k != "tax_code"}
    g = start(lead)
    for d in (TECH, MKT, DIR):
        s = resume(g, d)
    assert s["contract"]["legal_check"] == "NEEDS_REVIEW"
    assert s["invoices"][0]["status"] == "WAITING_TAX_CODE"


def test_gates_reject_direct_calls():
    with pytest.raises(GateError):
        contract_node({"quotation": {"status": "PENDING_APPROVAL"}})
    with pytest.raises(GateError):
        invoice_acceptance_node({"contract": {"status": "SIGNED"},
                                 "project": {"acceptance_status": "PENDING"}})


def test_state_survives_restart(tmp_path):
    db = tmp_path / "s.db"
    g1 = start(graph=build_graph(sqlite_checkpointer(db)), thread="HS-1")
    resume(g1, TECH, "HS-1")
    g2 = build_graph(sqlite_checkpointer(db))  # giả lập khởi động lại chương trình
    assert pending_approval(g2, "HS-1")["step"] == "quote"
    s = resume(g2, MKT, "HS-1")
    assert s["quotation"]["status"] == "APPROVED"


@pytest.mark.parametrize("kwh,status,has_incident", [(19_000, "NORMAL", False), (10_000, "ANOMALY", True)])
def test_om_monitoring(kwh, status, has_incident):
    out = build_om_graph().invoke({"project": {"project_id": "P1", "capacity_kwp": 160},
                                   "period": "11/2026", "monthly_kwh": kwh})
    assert out["production"]["status"] == status
    assert ("incident" in out) == has_incident


def test_cli_flow(tmp_path, capsys):
    db = str(tmp_path / "cli.db")
    lead = tmp_path / "lead.json"
    lead.write_text('{"id":"L-1","name":"ABC","tax_code":"0312345678","budget":2500000000,'
                    '"roof_area_m2":1000,"monthly_bill":60000000,"owns_roof":true}', encoding="utf-8")
    cli_main(["--db", db, "start", "--thread", "HS", "--lead", str(lead)])
    cli_main(["--db", db, "decide", "--thread", "HS", "--role", "TECH_HEAD", "--user", "A",
              "--approve", "--capacity", "150"])
    out = capsys.readouterr().out
    assert "Duyệt báo giá" in out
