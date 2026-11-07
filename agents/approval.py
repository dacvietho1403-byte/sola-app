"""Phân quyền và bước duyệt của người (human-in-the-loop) bằng interrupt() của LangGraph."""
from __future__ import annotations

import enum
from typing import Any

from langgraph.types import interrupt

from .state import log


class Role(enum.Enum):
    DIRECTOR = "Giám đốc / HĐQT"
    MARKETING_HEAD = "TP Thị trường"
    TECH_HEAD = "TP Quản lý Kỹ thuật"
    CHIEF_ACCOUNTANT = "Kế toán trưởng"
    AGENT_AI = "AI Agent"


# Bước duyệt -> các vai trò được phép duyệt. AI Agent không được duyệt bước nào.
APPROVAL_RIGHTS: dict[str, set[Role]] = {
    "survey": {Role.TECH_HEAD},
    "quote": {Role.MARKETING_HEAD, Role.DIRECTOR},
    "contract": {Role.DIRECTOR},
    "acceptance": {Role.TECH_HEAD},
    "finance": {Role.CHIEF_ACCOUNTANT},
}

STEP_LABELS = {
    "survey": "Xác nhận kết quả khảo sát thực địa",
    "quote": "Duyệt báo giá",
    "contract": "Ký hợp đồng",
    "acceptance": "Nghiệm thu thi công",
    "finance": "Duyệt báo cáo dòng tiền dự án",
}


def parse_role(value: Any) -> Role | None:
    if isinstance(value, Role):
        return value
    try:
        return Role[str(value).upper()]
    except KeyError:
        return None


def request_approval(step: str, summary: dict) -> tuple[dict | None, list[dict]]:
    """Dừng graph chờ người có thẩm quyền quyết định.

    Giá trị resume: {"role": "TECH_HEAD", "user": "Nguyễn Văn A", "approved": True, "note": "..."}
    cộng các trường riêng của từng bước.
    Sai quyền hoặc thiếu tên người duyệt: trả về (None, log từ chối). Node gọi retry() để
    ghi log ngay vào state và graph quay lại chính bước duyệt này.
    """
    allowed = APPROVAL_RIGHTS[step]
    answer = interrupt({
        "step": step,
        "label": STEP_LABELS[step],
        "allowed_roles": sorted(r.name for r in allowed),
        "summary": summary,
    }) or {}
    role = parse_role(answer.get("role"))
    user = str(answer.get("user") or "").strip()
    if role not in allowed or not user:
        return None, [log("HỆ THỐNG", f"Từ chối quyết định '{STEP_LABELS[step]}': sai quyền hoặc thiếu người duyệt",
                          {"role": answer.get("role"), "user": user or None,
                           "allowed_roles": sorted(r.name for r in allowed)})]
    approved = bool(answer.get("approved"))
    entry = log("NGƯỜI DUYỆT", f"{'Duyệt' if approved else 'Không duyệt'}: {STEP_LABELS[step]}",
                {k: v for k, v in answer.items() if k not in ("role", "user")},
                actor=user, role=role.value)
    return {**answer, "approved": approved, "user": user, "role": role.name}, [entry]


def retry(step: str, logs: list[dict]) -> dict:
    """Cập nhật state khi quyết định không hợp lệ: ghi log và đánh dấu hỏi lại bước này."""
    return {"approval_retry": step, "audit_logs": logs}
