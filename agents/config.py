"""Tham số nghiệp vụ. Mọi số tiền tính bằng đồng (int) để tránh sai số float.

Có thể ghi đè bằng biến môi trường tiền tố SOLA_ (ví dụ SOLA_VAT_RATE=0.08).
Giá trị mặc định đồng bộ với mô hình tài chính trong app.py.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, fields


@dataclass(frozen=True)
class Settings:
    # Báo giá (AI-06)
    unit_cost_per_kwp: int = 12_000_000          # giá vốn EPC, đ/kWp
    target_margin: float = 0.15                  # tỷ lệ cộng thêm trên giá vốn (markup)
    min_margin: float = 0.10                     # markup dưới mức này phải cảnh báo
    vat_rate: float = 0.10                       # điều chỉnh theo quy định hiện hành
    max_quote_revisions: int = 3

    # Thiết kế sơ bộ (AI-04, AI-05)
    specific_yield: float = 1450.0               # kWh/kWp/năm (Bình Dương, Đồng Nai, TP.HCM)
    roof_m2_per_kwp: float = 6.0                 # diện tích mái cần cho 1 kWp
    daytime_load_share: float = 0.70             # tỷ lệ điện tiêu thụ ban ngày
    grid_tariff: int = 2_000                     # giá điện EVN bình quân, đ/kWh

    # Chấm điểm lead (AI-04)
    lead_qualify_score: int = 60

    # Hợp đồng và thanh toán (AI-13, AI-11)
    payment_milestones: tuple = (
        ("advance", "Tạm ứng sau ký hợp đồng", 0.30),
        ("acceptance", "Thanh toán sau nghiệm thu", 0.65),
        ("retention", "Giữ lại bảo hành", 0.05),
    )
    warranty_months: int = 12
    seller_name: str = "Công ty Thuận Phong"
    seller_tax_code: str = ""                    # đặt SOLA_SELLER_TAX_CODE
    epc_contractor: str = "VSP / Thuận Phong"
    max_rework: int = 3

    # Vận hành (AI-08, AI-09)
    performance_threshold: float = 0.85          # sản lượng thực tế / kỳ vọng
    om_vendor: str = "Bảo trì Thuận Phong"
    sla_hours_critical: int = 4
    sla_hours_normal: int = 24

    # Đầu tư (AI-02)
    project_years: int = 20
    degradation: float = 0.0065
    tariff_growth: float = 0.025
    om_cost_per_kwp_year: int = 150_000
    om_cost_growth: float = 0.02

    # Đường dẫn
    db_path: str = field(default="data/sola_agents.db")


def load_settings() -> Settings:
    overrides = {}
    for f in fields(Settings):
        raw = os.environ.get(f"SOLA_{f.name.upper()}")
        if raw is None or f.name == "payment_milestones":
            continue
        typ = type(f.default)
        overrides[f.name] = typ(raw) if typ is not bool else raw.lower() in ("1", "true", "yes")
    s = Settings(**overrides)
    total = round(sum(p for _, _, p in s.payment_milestones), 6)
    if total != 1.0:
        raise ValueError(f"Tổng tỷ lệ thanh toán phải bằng 100%, hiện là {total:.0%}")
    return s


SETTINGS = load_settings()
