"""Dòng lệnh điều hành hệ thống multi-agent.

    python -m agents.cli demo
    python -m agents.cli start  --thread HS-001 --lead examples/lead_abc.json --campaign "Năng lượng Xanh Q4"
    python -m agents.cli status --thread HS-001
    python -m agents.cli decide --thread HS-001 --role TECH_HEAD --user "Nguyễn Văn A" --approve --capacity 160
    python -m agents.cli log    --thread HS-001
    python -m agents.cli monitor --thread HS-001 --kwh 18000 --period 11/2026
"""
from __future__ import annotations

import argparse
import json
import sys

from langgraph.types import Command

from .config import SETTINGS
from .graph import build_graph, pending_approval, sqlite_checkpointer
from .om import build_om_graph

DEMO_LEAD = {
    "id": "L-001", "name": "Công ty Sản xuất ABC", "tax_code": "0312345678",
    "budget": 2_500_000_000, "roof_area_m2": 1000, "monthly_bill": 60_000_000, "owns_roof": True,
}

DEMO_DECISIONS = [
    {"role": "AGENT_AI", "user": "AI-01", "approved": True},  # bị từ chối: AI không có quyền duyệt
    {"role": "TECH_HEAD", "user": "TP QLKT", "approved": True, "capacity_kwp": 160, "note": "Mái tôn tốt"},
    {"role": "MARKETING_HEAD", "user": "TP Thị trường", "approved": False, "revise_margin": 0.13},
    {"role": "MARKETING_HEAD", "user": "TP Thị trường", "approved": True},
    {"role": "DIRECTOR", "user": "Giám đốc", "approved": True},
    {"role": "TECH_HEAD", "user": "TP QLKT", "approved": False, "defects": ["Thiếu tiếp địa khung giàn"]},
    {"role": "TECH_HEAD", "user": "TP QLKT", "approved": True},
    {"role": "CHIEF_ACCOUNTANT", "user": "Kế toán trưởng", "approved": True},
]


def _cfg(thread: str) -> dict:
    return {"configurable": {"thread_id": thread}}


def _print(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _show_status(graph, thread: str) -> None:
    values = graph.get_state(_cfg(thread)).values
    if not values:
        print(f"Không tìm thấy hồ sơ {thread}")
        return
    print(f"Hồ sơ {thread} | giai đoạn: {values.get('stage')}")
    if values.get("stop_reason"):
        print(f"Lý do dừng: {values['stop_reason']}")
    req = pending_approval(graph, thread)
    if req:
        print(f"\nĐANG CHỜ DUYỆT: {req['label']} | vai trò được duyệt: {', '.join(req['allowed_roles'])}")
        _print(req["summary"])
    elif values.get("report"):
        print("\nBÁO CÁO GIÁM ĐỐC:")
        _print(values["report"])


def cmd_demo(_args) -> None:
    graph = build_graph()
    thread = "DEMO"
    graph.invoke({"campaign": "Chiến dịch Năng lượng Xanh Q4", "raw_lead": DEMO_LEAD}, _cfg(thread))
    for decision in DEMO_DECISIONS:
        req = pending_approval(graph, thread)
        if not req:
            break
        print(f"[CHỜ DUYỆT] {req['label']} -> {decision['user']} ({decision['role']}): "
              f"{'duyệt' if decision['approved'] else 'không duyệt'}")
        graph.invoke(Command(resume=decision), _cfg(thread))
    state = graph.get_state(_cfg(thread)).values
    print("\n=== NHẬT KÝ ===")
    for e in state["audit_logs"]:
        who = f"{e['actor']} [{e['role']}]" if e["role"] else e["agent"]
        print(f"{e['time']} | {who} | {e['action']}")
    print()
    _show_status(graph, thread)
    om = build_om_graph().invoke({"project": state["project"], "period": "11/2026", "monthly_kwh": 12_000})
    print("\n=== VẬN HÀNH KỲ 11/2026 ===")
    _print({"production": om["production"], "incident": om.get("incident")})


def cmd_start(args) -> None:
    graph = build_graph(sqlite_checkpointer(args.db))
    if graph.get_state(_cfg(args.thread)).values:
        sys.exit(f"Hồ sơ {args.thread} đã tồn tại, dùng lệnh status/decide")
    with open(args.lead, encoding="utf-8") as fh:
        lead = json.load(fh)
    graph.invoke({"campaign": args.campaign, "raw_lead": lead}, _cfg(args.thread))
    _show_status(graph, args.thread)


def cmd_status(args) -> None:
    _show_status(build_graph(sqlite_checkpointer(args.db)), args.thread)


def cmd_decide(args) -> None:
    graph = build_graph(sqlite_checkpointer(args.db))
    if not pending_approval(graph, args.thread):
        sys.exit(f"Hồ sơ {args.thread} không có bước nào đang chờ duyệt")
    decision = {"role": args.role, "user": args.user, "approved": args.approve, "note": args.note}
    if args.capacity is not None:
        decision["capacity_kwp"] = args.capacity
    if args.revise_margin is not None:
        decision["revise_margin"] = args.revise_margin
    if args.defect:
        decision["defects"] = args.defect
    graph.invoke(Command(resume=decision), _cfg(args.thread))
    _show_status(graph, args.thread)


def cmd_log(args) -> None:
    values = build_graph(sqlite_checkpointer(args.db)).get_state(_cfg(args.thread)).values
    _print(values.get("audit_logs", []))


def cmd_monitor(args) -> None:
    values = build_graph(sqlite_checkpointer(args.db)).get_state(_cfg(args.thread)).values
    project = values.get("project")
    if not project or project.get("acceptance_status") != "APPROVED":
        sys.exit("Dự án chưa nghiệm thu, chưa vào giai đoạn vận hành")
    out = build_om_graph().invoke({"project": project, "period": args.period,
                                   "monthly_kwh": args.kwh, "days": args.days})
    _print({"production": out["production"], "incident": out.get("incident")})


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="agents", description="Multi-Agent SOLA trên LangGraph")
    p.add_argument("--db", default=SETTINGS.db_path, help="File SQLite lưu trạng thái")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("demo", help="Chạy thử toàn bộ quy trình với quyết định mẫu").set_defaults(fn=cmd_demo)

    s = sub.add_parser("start", help="Mở hồ sơ mới từ file lead JSON")
    s.add_argument("--thread", required=True)
    s.add_argument("--lead", required=True)
    s.add_argument("--campaign")
    s.set_defaults(fn=cmd_start)

    for name, fn, hlp in (("status", cmd_status, "Xem trạng thái hồ sơ"), ("log", cmd_log, "Xem nhật ký")):
        x = sub.add_parser(name, help=hlp)
        x.add_argument("--thread", required=True)
        x.set_defaults(fn=fn)

    d = sub.add_parser("decide", help="Ra quyết định cho bước đang chờ duyệt")
    d.add_argument("--thread", required=True)
    d.add_argument("--role", required=True, help="TECH_HEAD, MARKETING_HEAD, DIRECTOR, CHIEF_ACCOUNTANT")
    d.add_argument("--user", required=True)
    g = d.add_mutually_exclusive_group(required=True)
    g.add_argument("--approve", action="store_true")
    g.add_argument("--reject", dest="approve", action="store_false")
    d.add_argument("--note")
    d.add_argument("--capacity", type=float, help="Công suất khảo sát thực tế (kWp)")
    d.add_argument("--revise-margin", type=float, help="Biên lợi nhuận khi yêu cầu lập lại báo giá")
    d.add_argument("--defect", action="append", help="Tồn tại nghiệm thu (lặp lại được)")
    d.set_defaults(fn=cmd_decide)

    m = sub.add_parser("monitor", help="Nhập sản lượng tháng để giám sát vận hành")
    m.add_argument("--thread", required=True)
    m.add_argument("--kwh", type=float, required=True)
    m.add_argument("--days", type=int, default=30)
    m.add_argument("--period")
    m.set_defaults(fn=cmd_monitor)

    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
