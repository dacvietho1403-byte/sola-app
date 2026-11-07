"""State dùng chung của graph và tiện ích ghi audit log."""
from __future__ import annotations

import operator
import uuid
from datetime import datetime
from typing import Annotated, Any, Optional, TypedDict
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")


class PipelineState(TypedDict, total=False):
    # Đầu vào
    campaign: Optional[str]
    raw_lead: dict
    # Kết quả từng agent
    content_plan: dict
    lead: dict
    survey: dict
    quotation: dict
    margin_override: Optional[float]
    contract: dict
    project: dict
    invoices: Annotated[list[dict], operator.add]
    finance: dict
    investment: dict
    report: dict
    # Điều phối
    stage: str
    stop_reason: Optional[str]
    approval_retry: Optional[str]      # bước duyệt cần hỏi lại do quyết định không hợp lệ
    audit_logs: Annotated[list[dict], operator.add]


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    """Mã chứng từ không trùng: PREFIX-YYYYMMDD-xxxxxx."""
    return f"{prefix}-{datetime.now(TZ):%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"


def log(agent: str, action: str, data: Any = None, *, actor: str | None = None,
        role: str | None = None) -> dict:
    return {
        "time": now_iso(),
        "agent": agent,
        "actor": actor or agent,
        "role": role,
        "action": action,
        "data": data,
    }


class GateError(RuntimeError):
    """Vi phạm điều kiện tiên quyết của quy trình (ví dụ xuất hóa đơn khi chưa ký HĐ)."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)
