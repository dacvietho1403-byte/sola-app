"""Các node (agent) của luồng chính.

Quy ước:
- Node có interrupt() (bước duyệt) chạy lại từ đầu khi resume, nên không sinh mã ngẫu nhiên
  và không có tác động bên ngoài trước interrupt.
- Mỗi node tự kiểm tra điều kiện tiên quyết bằng require(), không tin hoàn toàn vào cạnh graph.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

import numpy_financial as npf

from .approval import request_approval, retry
from .config import SETTINGS as S
from .state import PipelineState, log, new_id, now_iso, require

LEAD_REQUIRED = ("id", "name", "budget", "roof_area_m2", "monthly_bill", "owns_roof")


def vnd(x: float | Decimal) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def size_system(roof_area_m2: float, monthly_bill: float) -> dict:
    """Công suất sơ bộ = min(theo diện tích mái, theo nhu cầu điện ban ngày)."""
    by_roof = roof_area_m2 / S.roof_m2_per_kwp
    monthly_kwh = monthly_bill / S.grid_tariff
    by_load = monthly_kwh * 12 * S.daytime_load_share / S.specific_yield
    return {
        "kwp_by_roof": round(by_roof, 1),
        "kwp_by_load": round(by_load, 1),
        "capacity_kwp": round(min(by_roof, by_load), 1),
    }


def price_for(capacity_kwp: float, margin: float) -> dict:
    cost = vnd(Decimal(str(capacity_kwp)) * S.unit_cost_per_kwp)
    before_vat = vnd(Decimal(cost) * (1 + Decimal(str(margin))))
    vat = vnd(Decimal(before_vat) * Decimal(str(S.vat_rate)))
    return {"estimated_cost": cost, "price_before_vat": before_vat, "vat": vat,
            "total_price": before_vat + vat}


# ---------------------------------------------------------------- AI-03
def marketing_node(state: PipelineState) -> dict:
    campaign = state.get("campaign")
    if not campaign:
        return {}
    plan = {
        "campaign": campaign,
        "channels": ["Facebook/Zalo Ads", "Google Search", "Hội thảo KCN"],
        "kpi_qualified_leads_per_month": 50,
        "posts_count": 12,
        "brief_to": "Agency quảng cáo",
    }
    return {"content_plan": plan,
            "audit_logs": [log("AI-03 Nội dung Marketing", "Lập kế hoạch nội dung và brief agency", plan)]}


# ---------------------------------------------------------------- AI-04
def lead_filter_node(state: PipelineState) -> dict:
    agent = "AI-04 CSKH & Lọc khách"
    raw = state.get("raw_lead") or {}
    missing = [k for k in LEAD_REQUIRED if raw.get(k) in (None, "")]
    if missing:
        reason = f"Lead thiếu thông tin bắt buộc: {', '.join(missing)}"
        return {"stage": "STOPPED", "stop_reason": reason,
                "lead": {**raw, "status": "INCOMPLETE"},
                "audit_logs": [log(agent, "Dừng: lead thiếu dữ liệu", {"missing": missing})]}

    sizing = size_system(float(raw["roof_area_m2"]), float(raw["monthly_bill"]))
    est = price_for(sizing["capacity_kwp"], S.target_margin)
    budget = float(raw["budget"])
    budget_ratio = budget / est["total_price"] if est["total_price"] else 0

    breakdown = {
        "budget": 40 if budget_ratio >= 1 else 25 if budget_ratio >= 0.7 else 10 if budget_ratio >= 0.4 else 0,
        "monthly_bill": 25 if raw["monthly_bill"] >= 50e6 else 15 if raw["monthly_bill"] >= 20e6
        else 5 if raw["monthly_bill"] >= 5e6 else 0,
        "roof_ownership": 20 if raw["owns_roof"] else 5,
        "roof_area": 15 if raw["roof_area_m2"] >= 300 else 8 if raw["roof_area_m2"] >= 100 else 0,
    }
    score = sum(breakdown.values())
    qualified = score >= S.lead_qualify_score
    lead = {**raw, **sizing, "estimated_total_price": est["total_price"],
            "budget_coverage": round(budget_ratio, 2), "score": score,
            "score_breakdown": breakdown, "status": "QUALIFIED" if qualified else "UNQUALIFIED"}
    if not raw.get("tax_code"):
        lead["warnings"] = ["Chưa có mã số thuế khách hàng, cần bổ sung trước khi xuất hóa đơn"]
    update = {"lead": lead,
              "audit_logs": [log(agent, "Lead đạt chuẩn" if qualified else "Loại lead không đạt chuẩn",
                                 {"lead_id": raw["id"], "score": score, "breakdown": breakdown})]}
    if qualified:
        update["stage"] = "LEAD_QUALIFIED"
    else:
        update.update(stage="STOPPED", stop_reason=f"Lead {score} điểm, dưới ngưỡng {S.lead_qualify_score}")
    return update


# ---------------------------------------------------------------- AI-05
def survey_request_node(state: PipelineState) -> dict:
    lead = state["lead"]
    require(lead.get("status") == "QUALIFIED", "Chỉ đặt lịch khảo sát cho lead đã đạt chuẩn")
    survey = {
        "survey_id": new_id("SV"),
        "lead_id": lead["id"],
        "customer_name": lead["name"],
        "assigned_to": ["TP Thị trường", "TP Quản lý Kỹ thuật"],
        "proposed_capacity_kwp": lead["capacity_kwp"],
        "crm_stage": "SURVEY_SCHEDULED",
        "status": "SCHEDULED",
    }
    return {"survey": survey, "stage": "SURVEY_SCHEDULED",
            "audit_logs": [log("AI-05 CRM & Bán hàng", "Đặt lịch khảo sát và chuyển trạng thái CRM", survey)]}


def survey_result_node(state: PipelineState) -> dict:
    survey = state["survey"]
    decision, logs = request_approval("survey", {
        "customer": survey["customer_name"],
        "proposed_capacity_kwp": survey["proposed_capacity_kwp"],
        "hint": "Nhập capacity_kwp thực tế sau khảo sát; approved=false nếu mái không đủ điều kiện",
    })
    if decision is None:
        return retry("survey", logs)
    if not decision["approved"]:
        return {"survey": {**survey, "status": "SITE_UNSUITABLE", "note": decision.get("note")},
                "stage": "STOPPED", "stop_reason": "Khảo sát: mái không đủ điều kiện lắp đặt",
                "audit_logs": logs}
    capacity = float(decision.get("capacity_kwp") or survey["proposed_capacity_kwp"])
    require(capacity > 0, "Công suất khảo sát phải lớn hơn 0")
    return {"survey": {**survey, "status": "COMPLETED", "capacity_kwp": capacity,
                       "surveyed_by": decision["user"], "note": decision.get("note")},
            "stage": "SURVEY_COMPLETED", "audit_logs": logs}


# ---------------------------------------------------------------- AI-06
def quotation_node(state: PipelineState) -> dict:
    survey = state["survey"]
    require(survey.get("status") == "COMPLETED", "Chưa có kết quả khảo sát, không thể báo giá")
    lead = state["lead"]
    prev = state.get("quotation") or {}
    margin = state.get("margin_override") or S.target_margin
    price = price_for(survey["capacity_kwp"], margin)
    warnings = []
    if price["total_price"] > lead["budget"]:
        over = price["total_price"] / lead["budget"] - 1
        warnings.append(f"Vượt ngân sách khách {over:.0%} ({lead['budget']:,.0f} đ)")
    if margin < S.min_margin:
        warnings.append(f"Biên lợi nhuận {margin:.0%} thấp hơn mức tối thiểu {S.min_margin:.0%}")
    quotation = {
        "quote_id": new_id("Q"),
        "revision": prev.get("revision", 0) + 1,
        "customer_name": lead["name"],
        "capacity_kwp": survey["capacity_kwp"],
        "unit_cost_per_kwp": S.unit_cost_per_kwp,
        "margin": margin,
        "vat_rate": S.vat_rate,
        **price,
        "warnings": warnings,
        "status": "PENDING_APPROVAL",
    }
    return {"quotation": quotation, "stage": "QUOTE_PENDING",
            "audit_logs": [log("AI-06 Phân tích & Báo giá", "Lập báo giá, chờ duyệt", quotation)]}


def approve_quote_node(state: PipelineState) -> dict:
    q = state["quotation"]
    decision, logs = request_approval("quote", {
        "quote_id": q["quote_id"], "revision": q["revision"], "capacity_kwp": q["capacity_kwp"],
        "price_before_vat": q["price_before_vat"], "total_price": q["total_price"],
        "margin": q["margin"], "warnings": q["warnings"],
        "hint": "approved=false kèm revise_margin=0.12 để yêu cầu lập lại báo giá",
    })
    if decision is None:
        return retry("quote", logs)
    meta = {"decided_by": decision["user"], "decided_at": now_iso(), "note": decision.get("note")}
    if decision["approved"]:
        return {"quotation": {**q, **meta, "status": "APPROVED"}, "stage": "QUOTE_APPROVED", "audit_logs": logs}
    revise = decision.get("revise_margin")
    if revise is not None and q["revision"] < S.max_quote_revisions:
        return {"quotation": {**q, **meta, "status": "REVISION_REQUESTED"},
                "margin_override": float(revise), "stage": "QUOTE_REVISION", "audit_logs": logs}
    return {"quotation": {**q, **meta, "status": "REJECTED"}, "stage": "STOPPED",
            "stop_reason": "Báo giá không được duyệt", "audit_logs": logs}


# ---------------------------------------------------------------- AI-13
def contract_node(state: PipelineState) -> dict:
    q = state["quotation"]
    require(q.get("status") == "APPROVED", "Báo giá chưa được duyệt, không thể lập hợp đồng")
    lead = state["lead"]
    schedule = [{"milestone": k, "label": label, "ratio": r,
                 "amount_before_vat": vnd(Decimal(q["price_before_vat"]) * Decimal(str(r)))}
                for k, label, r in S.payment_milestones]
    # Dồn phần lẻ làm tròn vào đợt cuối để tổng khớp đúng giá trị hợp đồng
    schedule[-1]["amount_before_vat"] += q["price_before_vat"] - sum(m["amount_before_vat"] for m in schedule)

    issues = []
    if not lead.get("tax_code"):
        issues.append("Thiếu mã số thuế bên mua")
    if not S.seller_tax_code:
        issues.append("Chưa cấu hình mã số thuế bên bán (SOLA_SELLER_TAX_CODE)")
    if sum(m["amount_before_vat"] for m in schedule) != q["price_before_vat"]:
        issues.append("Tổng các đợt thanh toán không khớp giá trị hợp đồng")

    contract = {
        "contract_id": new_id("CTR"),
        "quote_ref": q["quote_id"],
        "customer": lead["name"],
        "customer_tax_code": lead.get("tax_code"),
        "capacity_kwp": q["capacity_kwp"],
        "value_before_vat": q["price_before_vat"],
        "vat": q["vat"],
        "value": q["total_price"],
        "payment_schedule": schedule,
        "warranty_months": S.warranty_months,
        "legal_check": "PASSED" if not issues else "NEEDS_REVIEW",
        "legal_issues": issues,
        "status": "PENDING_DIRECTOR_SIGNATURE",
    }
    return {"contract": contract, "stage": "CONTRACT_PENDING",
            "audit_logs": [log("AI-13 Hợp đồng & Pháp lý", "Soạn thảo hợp đồng, chờ Giám đốc ký", contract)]}


def sign_contract_node(state: PipelineState) -> dict:
    c = state["contract"]
    decision, logs = request_approval("contract", {
        "contract_id": c["contract_id"], "customer": c["customer"], "value": c["value"],
        "legal_check": c["legal_check"], "legal_issues": c["legal_issues"],
    })
    if decision is None:
        return retry("contract", logs)
    if not decision["approved"]:
        return {"contract": {**c, "status": "CANCELLED", "note": decision.get("note")},
                "stage": "STOPPED", "stop_reason": "Giám đốc không ký hợp đồng", "audit_logs": logs}
    return {"contract": {**c, "status": "SIGNED", "signed_by": decision["user"], "signed_at": now_iso()},
            "stage": "CONTRACT_SIGNED", "audit_logs": logs}


# ---------------------------------------------------------------- AI-11
def _invoice(state: PipelineState, milestone: str, status: str, due_date: str | None = None) -> dict:
    c = state["contract"]
    m = next(x for x in c["payment_schedule"] if x["milestone"] == milestone)
    vat = vnd(Decimal(m["amount_before_vat"]) * Decimal(str(S.vat_rate)))
    buyer_tax = c.get("customer_tax_code")
    if status == "READY_TO_ISSUE" and not buyer_tax:
        status = "WAITING_TAX_CODE"
    return {
        "invoice_id": new_id("INV"),
        "contract_ref": c["contract_id"],
        "milestone": milestone,
        "label": m["label"],
        "amount_before_vat": m["amount_before_vat"],
        "vat": vat,
        "amount": m["amount_before_vat"] + vat,
        "seller": S.seller_name,
        "seller_tax_code": S.seller_tax_code or None,
        "buyer_tax_code": buyer_tax,
        "acceptance_ref": (state.get("project") or {}).get("acceptance_doc_id"),
        "due_date": due_date,
        "status": status,
        "payment_status": "UNPAID",
    }


def invoice_advance_node(state: PipelineState) -> dict:
    require(state["contract"].get("status") == "SIGNED", "Hợp đồng chưa ký, không thể xuất hóa đơn tạm ứng")
    inv = _invoice(state, "advance", "READY_TO_ISSUE")
    return {"invoices": [inv], "stage": "ADVANCE_INVOICED",
            "audit_logs": [log("AI-11 Hóa đơn & Thu tiền", "Lập hóa đơn tạm ứng", inv)]}


def invoice_acceptance_node(state: PipelineState) -> dict:
    require(state["contract"].get("status") == "SIGNED", "Hợp đồng chưa ký")
    require((state.get("project") or {}).get("acceptance_status") == "APPROVED",
            "Chưa nghiệm thu, không thể xuất hóa đơn thanh toán")
    acc = _invoice(state, "acceptance", "READY_TO_ISSUE")
    today = date.today()
    month = today.month - 1 + S.warranty_months
    try:
        due = today.replace(year=today.year + month // 12, month=month % 12 + 1)
    except ValueError:  # ngày 29-31 không có ở tháng đích
        due = today.replace(year=today.year + month // 12, month=month % 12 + 1, day=28)
    ret = _invoice(state, "retention", "SCHEDULED", due_date=due.isoformat())
    return {"invoices": [acc, ret], "stage": "ACCEPTANCE_INVOICED",
            "audit_logs": [log("AI-11 Hóa đơn & Thu tiền", "Lập hóa đơn nghiệm thu và lịch thu tiền bảo hành",
                               {"acceptance": acc, "retention": ret})]}


# ---------------------------------------------------------------- AI-07
def construction_node(state: PipelineState) -> dict:
    c = state["contract"]
    require(c.get("status") == "SIGNED", "Hợp đồng chưa ký, không thể triển khai thi công")
    prev = state.get("project")
    if prev:
        project = {**prev, "rework_count": prev["rework_count"] + 1, "status": "REWORK",
                   "acceptance_status": "PENDING"}
        action = f"Khắc phục tồn tại lần {project['rework_count']}"
    else:
        project = {
            "project_id": new_id("PRJ"),
            "contract_ref": c["contract_id"],
            "customer": c["customer"],
            "capacity_kwp": c["capacity_kwp"],
            "contractor": S.epc_contractor,
            "rework_count": 0,
            "status": "IN_PROGRESS",
            "acceptance_status": "PENDING",
        }
        action = "Khởi tạo dự án và giao nhà thầu thi công"
    return {"project": project, "stage": "CONSTRUCTION",
            "audit_logs": [log("AI-07 Dự án & Nghiệm thu", action, project)]}


def acceptance_node(state: PipelineState) -> dict:
    p = state["project"]
    decision, logs = request_approval("acceptance", {
        "project_id": p["project_id"], "customer": p["customer"], "capacity_kwp": p["capacity_kwp"],
        "rework_count": p["rework_count"],
        "hint": "approved=false kèm defects=[...] để yêu cầu khắc phục",
    })
    if decision is None:
        return retry("acceptance", logs)
    doc_id = f"ACC-{p['project_id']}-{p['rework_count'] + 1}"
    if decision["approved"]:
        return {"project": {**p, "status": "COMPLETED", "acceptance_status": "APPROVED",
                            "acceptance_doc_id": doc_id, "accepted_by": decision["user"],
                            "accepted_at": now_iso()},
                "stage": "ACCEPTED", "audit_logs": logs}
    defects = decision.get("defects") or []
    project = {**p, "acceptance_status": "REJECTED", "defects": defects}
    if p["rework_count"] + 1 >= S.max_rework:
        return {"project": project, "stage": "STOPPED",
                "stop_reason": f"Nghiệm thu không đạt sau {S.max_rework} lần, cần Giám đốc xử lý",
                "audit_logs": logs}
    return {"project": project, "stage": "REWORK_REQUIRED", "audit_logs": logs}


# ---------------------------------------------------------------- AI-10
def finance_node(state: PipelineState) -> dict:
    c, q = state["contract"], state["quotation"]
    invoices = state.get("invoices") or []
    invoiced = [i for i in invoices if i["status"] != "SCHEDULED"]
    revenue = c["value_before_vat"]
    cost = q["estimated_cost"]
    finance = {
        "project_id": state["project"]["project_id"],
        "revenue_before_vat": revenue,
        "estimated_cost": cost,
        "gross_profit": revenue - cost,
        "gross_margin": round((revenue - cost) / revenue, 4) if revenue else 0,
        "invoiced_before_vat": sum(i["amount_before_vat"] for i in invoiced),
        "receivable_scheduled": sum(i["amount"] for i in invoices if i["status"] == "SCHEDULED"),
        "output_vat": sum(i["vat"] for i in invoiced),
        "status": "DRAFT_PENDING_CHIEF_ACCOUNTANT",
    }
    return {"finance": finance, "stage": "FINANCE_PENDING",
            "audit_logs": [log("AI-10 Kế toán & Thù lao", "Lập báo cáo dòng tiền dự án, chờ Kế toán trưởng", finance)]}


def approve_finance_node(state: PipelineState) -> dict:
    f = state["finance"]
    decision, logs = request_approval("finance", f)
    if decision is None:
        return retry("finance", logs)
    if not decision["approved"]:
        return {"finance": {**f, "status": "RETURNED", "note": decision.get("note")},
                "stage": "STOPPED", "stop_reason": "Kế toán trưởng trả lại báo cáo dòng tiền",
                "audit_logs": logs}
    return {"finance": {**f, "status": "APPROVED", "approved_by": decision["user"]},
            "stage": "FINANCE_APPROVED", "audit_logs": logs}


# ---------------------------------------------------------------- AI-02
def customer_cashflows(capacity_kwp: float, investment: int) -> list[float]:
    flows = [-float(investment)]
    for t in range(S.project_years):
        kwh = capacity_kwp * S.specific_yield * (1 - S.degradation) ** t
        saving = kwh * S.grid_tariff * (1 + S.tariff_growth) ** t
        om = capacity_kwp * S.om_cost_per_kwp_year * (1 + S.om_cost_growth) ** t
        flows.append(saving - om)
    return flows


def investment_node(state: PipelineState) -> dict:
    c = state["contract"]
    flows = customer_cashflows(c["capacity_kwp"], c["value_before_vat"])
    irr = float(npf.irr(flows))
    cumulative, payback = flows[0], None
    for year, cf in enumerate(flows[1:], start=1):
        if cumulative + cf >= 0:
            payback = round(year - 1 + (-cumulative) / cf, 1)
            break
        cumulative += cf
    model = {
        "basis": "Hiệu quả đầu tư phía khách hàng (tự dùng, giá trước VAT)",
        "years": S.project_years,
        "first_year_kwh": round(c["capacity_kwp"] * S.specific_yield),
        "first_year_saving": vnd(flows[1]),
        "irr": round(irr, 4),
        "payback_years": payback,
        "status": "READY_FOR_INVESTORS",
    }
    return {"investment": model, "stage": "INVESTMENT_UPDATED",
            "audit_logs": [log("AI-02 Đầu tư & Gọi vốn", "Cập nhật mô hình tài chính dự án", model)]}


# ---------------------------------------------------------------- AI-01
def executive_report_node(state: PipelineState) -> dict:
    invoices = state.get("invoices") or []
    report = {
        "customer": state["lead"]["name"],
        "capacity_kwp": state["contract"]["capacity_kwp"],
        "contract_value": state["contract"]["value"],
        "gross_margin": state["finance"]["gross_margin"],
        "invoices_ready": sum(1 for i in invoices if i["status"] == "READY_TO_ISSUE"),
        "invoices_waiting_tax_code": sum(1 for i in invoices if i["status"] == "WAITING_TAX_CODE"),
        "unpaid_amount": sum(i["amount"] for i in invoices if i["payment_status"] == "UNPAID"),
        "rework_count": state["project"]["rework_count"],
        "customer_irr": state["investment"]["irr"],
        "customer_payback_years": state["investment"]["payback_years"],
        "human_decisions": sum(1 for e in state.get("audit_logs", []) if e["agent"] == "NGƯỜI DUYỆT"),
    }
    return {"report": report, "stage": "COMPLETED",
            "audit_logs": [log("AI-01 Trợ lý điều hành", "Tổng hợp báo cáo trình Giám đốc", report)]}
