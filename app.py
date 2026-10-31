import streamlit as st
import pandas as pd
import numpy as np
import numpy_financial as npf
import plotly.graph_objects as go

# =====================================================================
# 1. CAU HINH TRANG
# =====================================================================
st.set_page_config(
    page_title="Solar Rental Expert Strategy & Finance System",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
    <style>
    .main-title { font-size:2.2rem !important; font-weight: 700; color: #1E3A8A; margin-bottom: 5px; }
    .sub-title { font-size:1.1rem !important; color: #4B5563; margin-bottom: 25px; }
    .metric-card { background-color: #F8FAFC; padding: 15px; border-radius: 8px; border-left: 5px solid #3B82F6; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    .strat-card { background-color: #EFF6FF; padding: 18px; border-radius: 8px; border-left: 5px solid #1D4ED8; margin-bottom: 15px; }
    .risk-card { background-color: #FEF2F2; padding: 18px; border-radius: 8px; border-left: 5px solid #DC2626; margin-bottom: 15px; }
    </style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">HỆ THỐNG HOẠCH ĐỊNH CHIẾN LƯỢC & TÀI CHÍNH SOLAR TOÀN DIỆN</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Bản hoàn chỉnh: IRR, NPV, DSCR, thuế ưu đãi ngành xanh, chuyển lỗ 5 năm, độ nhạy</p>', unsafe_allow_html=True)
st.markdown("---")

# =====================================================================
# 2. SIDEBAR - THAM SO DAU VAO
# =====================================================================
st.sidebar.header("THAM SỐ ĐẦU VÀO DỰ ÁN")

tinh_thanh_radiation = {
    "Bình Dương / Đồng Nai / TP.HCM (1,450 kWh/kWp/năm)": 1450,
    "Long An / Tây Ninh / Bà Rịa (1,500 kWh/kWp/năm)": 1500,
    "Ninh Thuận / Bình Thuận (1,600 kWh/kWp/năm)": 1600,
    "Khu vực Miền Trung (1,300 kWh/kWp/năm)": 1300,
    "Khu vực Miền Bắc (1,100 kWh/kWp/năm)": 1100,
}
selected_region = st.sidebar.selectbox("Vị trí địa lý dự án (Bức xạ)", list(tinh_thanh_radiation.keys()))
nang_suat_phat = tinh_thanh_radiation[selected_region]

model_type = st.sidebar.selectbox(
    "Mô hình cho thuê chủ đạo",
    ["B2B PPA (Bán điện nhà xưởng theo tỷ lệ chiết khấu EVN)",
     "B2B Leasing (Cho thuê cố định theo công suất/tháng)"],
)
is_ppa = "PPA" in model_type

st.sidebar.markdown("---")
st.sidebar.subheader("Kỹ thuật & Quy mô")
he_so_kWP = st.sidebar.number_input("Quy mô hệ thống (kWp)", min_value=10, max_value=20000, value=1000, step=100)
suat_dau_tu = st.sidebar.number_input("Suất đầu tư (Triệu VNĐ/kWp)", min_value=8.0, max_value=40.0, value=13.5, step=0.5)
suy_hao_hang_nam = st.sidebar.slider("Suy hao tấm pin hằng năm (%)", 0.4, 1.0, 0.65, step=0.05) / 100
thoi_gian_mo_phong = int(st.sidebar.slider("Thời hạn mô phỏng dự án (Năm)", 10, 25, 20, step=1))
wacc_rate = st.sidebar.number_input("Tỷ lệ chiết khấu tính NPV (%)", min_value=5.0, max_value=20.0, value=10.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.subheader("Doanh thu & O&M")
truong_gia_dien = st.sidebar.slider("Tăng giá điện hằng năm (%)", 0.0, 5.0, 2.5, step=0.1)
truong_gia_opex = st.sidebar.slider("Tăng chi phí O&M hằng năm (%)", 0.0, 5.0, 2.0, step=0.1)

gia_ban_nam_dau = 0.0
phi_leasing_kwp_thang = 0.0
if is_ppa:
    st.sidebar.caption("Biểu giá điện sản xuất EVN (dưới 6kV). Solar không phát giờ thấp điểm (đêm).")
    gia_cao_diem = st.sidebar.number_input("Giá giờ Cao Điểm (VNĐ/kWh)", value=3300)
    gia_binh_thuong = st.sidebar.number_input("Giá giờ Bình Thường (VNĐ/kWh)", value=1700)
    pct_cao_diem = st.sidebar.slider("% sản lượng phát vào giờ Cao Điểm", 0, 100, 20)
    chiet_khau_ppa = st.sidebar.slider("Chiết khấu giá cho khách hàng (%)", 0, 30, 15)
    gia_evn_tb = gia_cao_diem * pct_cao_diem / 100 + gia_binh_thuong * (100 - pct_cao_diem) / 100
    gia_ban_nam_dau = gia_evn_tb * (1 - chiet_khau_ppa / 100)
    st.sidebar.info(f"Giá bán PPA bình quân năm đầu: {gia_ban_nam_dau:,.0f} VNĐ/kWh")
else:
    phi_leasing_kwp_thang = st.sidebar.number_input("Phí thuê mái cố định (VNĐ/kWp/tháng)", value=160000, step=5000)

chi_phi_om_kwp = st.sidebar.number_input("Chi phí O&M cố định (VNĐ/kWp/năm)", value=150000, step=10000)
chi_phi_bh_rate = st.sidebar.slider("Bảo hiểm tài sản năm 1 (% trên CAPEX)", 0.1, 1.0, 0.25, step=0.05)
chi_phi_inverter_kwp = st.sidebar.number_input("Chi phí thay Inverter năm 10 (VNĐ/kWp)", value=1200000, step=100000)

st.sidebar.markdown("---")
st.sidebar.subheader("Cấu trúc vốn, Khấu hao & Thuế")
ti_le_vay = st.sidebar.slider("Tỷ lệ vốn vay ngân hàng (%)", 0, 80, 70, step=5)
lai_suat_vay = st.sidebar.number_input("Lãi suất vay năm (%)", min_value=4.0, max_value=15.0, value=8.5, step=0.5)
thoi_han_vay = int(st.sidebar.number_input(
    "Thời hạn vay vốn (Năm)", min_value=3, max_value=thoi_gian_mo_phong,
    value=min(8, thoi_gian_mo_phong), step=1))
thoi_gian_khau_hao = int(st.sidebar.number_input(
    "Thời gian khấu hao TSCĐ chính (Năm)", min_value=5, max_value=thoi_gian_mo_phong,
    value=min(12, thoi_gian_mo_phong), step=1))

st.sidebar.caption("Ưu đãi thuế TNDN năng lượng xanh")
uu_dai_thue = st.sidebar.checkbox(
    "Áp dụng ưu đãi (thuế 10% trong 15 năm; miễn 4 năm, giảm 50% trong 9 năm tiếp theo)", value=True)
thue_suat_goc = st.sidebar.number_input("Thuế suất TNDN phổ thông (%)", min_value=10, max_value=25, value=20, step=1)


# =====================================================================
# 3. HAM TINH THUE (DUNG CHUNG CHO DU AN VA VON CHU)
# =====================================================================
def tinh_thue_tndn(ebitda_s, interest_s, deprec_s, uu_dai, thue_goc, han_lo=5):
    """Tinh thue TNDN tung nam, co chuyen lo toi da han_lo nam va lo trinh uu dai."""
    n_years = len(ebitda_s)
    ebt_s = [ebitda_s[i] - interest_s[i] - deprec_s[i] for i in range(n_years)]

    first_taxable = None
    for i, e in enumerate(ebt_s):
        if e > 0:
            first_taxable = i + 1
            break
    mien_tu = min(first_taxable, 4) if first_taxable else 4

    taxes = []
    loss_pool = {}
    for idx, ebt in enumerate(ebt_s):
        nam = idx + 1
        # xoa lo qua han
        for y in list(loss_pool.keys()):
            if nam - y > han_lo:
                del loss_pool[y]

        if ebt <= 0:
            if ebt < 0:
                loss_pool[nam] = -ebt
            taxes.append(0.0)
            continue

        thu_nhap = ebt
        for y in sorted(loss_pool.keys()):
            if thu_nhap <= 0:
                break
            bu = min(loss_pool[y], thu_nhap)
            loss_pool[y] -= bu
            thu_nhap -= bu
        loss_pool = {y: v for y, v in loss_pool.items() if v > 0}

        if uu_dai:
            k = nam - mien_tu + 1
            if nam > 15:
                rate = thue_goc / 100
            elif k <= 4:
                rate = 0.0
            elif k <= 13:
                rate = 0.05
            else:
                rate = 0.10
        else:
            rate = thue_goc / 100
        taxes.append(thu_nhap * rate)
    return taxes


# =====================================================================
# 4. MO HINH TAI CHINH
# =====================================================================
def run_model(suat, price_mult=1.0):
    capex = he_so_kWP * suat * 1_000_000
    von_vay = capex * ti_le_vay / 100
    von_tu_co = capex - von_vay

    if von_vay > 0:
        r = lai_suat_vay / 100
        n = thoi_han_vay
        annuity = von_vay * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    else:
        annuity = 0.0

    prod, rev, opex, ebitda_l = [], [], [], []
    interest_l, principal_l, service_l = [], [], []
    deprec_l, capex_inv_l = [], []
    du_no = von_vay

    for nam in range(1, thoi_gian_mo_phong + 1):
        sl = he_so_kWP * nang_suat_phat * (1 - suy_hao_hang_nam) ** (nam - 1)
        g_dt = (1 + truong_gia_dien / 100) ** (nam - 1)
        g_op = (1 + truong_gia_opex / 100) ** (nam - 1)

        if is_ppa:
            dt = sl * gia_ban_nam_dau * g_dt * price_mult
        else:
            dt = he_so_kWP * phi_leasing_kwp_thang * 12 * g_dt * price_mult

        om = he_so_kWP * chi_phi_om_kwp * g_op
        ti_le_con_lai = max(0.3, 1 - (nam - 1) / thoi_gian_khau_hao)
        bh = capex * (chi_phi_bh_rate / 100) * ti_le_con_lai * g_op
        tong_opex = om + bh

        inv_cost = he_so_kWP * chi_phi_inverter_kwp
        capex_inv = inv_cost if nam == 10 else 0.0
        kh_inv = inv_cost / 5 if 10 <= nam <= 14 else 0.0
        kh_main = capex / thoi_gian_khau_hao if nam <= thoi_gian_khau_hao else 0.0

        if nam <= thoi_han_vay and von_vay > 0:
            lai = du_no * lai_suat_vay / 100
            if nam == thoi_han_vay:
                goc = du_no
                service = goc + lai
            else:
                goc = annuity - lai
                service = annuity
            du_no -= goc
        else:
            lai, goc, service = 0.0, 0.0, 0.0

        prod.append(sl)
        rev.append(dt)
        opex.append(tong_opex)
        ebitda_l.append(dt - tong_opex)
        interest_l.append(lai)
        principal_l.append(goc)
        service_l.append(service)
        deprec_l.append(kh_main + kh_inv)
        capex_inv_l.append(capex_inv)

    zeros = [0.0] * thoi_gian_mo_phong
    tax_proj = tinh_thue_tndn(ebitda_l, zeros, deprec_l, uu_dai_thue, thue_suat_goc)
    tax_eq = tinh_thue_tndn(ebitda_l, interest_l, deprec_l, uu_dai_thue, thue_suat_goc)

    cfs_project = [-capex]
    cfs_equity = [-von_tu_co]
    rows = []
    tich_luy = -von_tu_co
    hoan_von = "Không hoàn vốn"
    am_lai = False

    for i in range(thoi_gian_mo_phong):
        nam = i + 1
        cf_p = ebitda_l[i] - tax_proj[i] - capex_inv_l[i]
        cf_e = ebitda_l[i] - service_l[i] - tax_eq[i] - capex_inv_l[i]
        cfs_project.append(cf_p)
        cfs_equity.append(cf_e)

        truoc = tich_luy
        tich_luy += cf_e
        if truoc < 0 <= tich_luy and hoan_von == "Không hoàn vốn":
            hoan_von = f"{nam - 1 + abs(truoc) / cf_e:.1f} Năm"
        if hoan_von != "Không hoàn vốn" and tich_luy < 0:
            am_lai = True

        cfads = ebitda_l[i] - tax_eq[i] - capex_inv_l[i]
        dscr = cfads / service_l[i] if service_l[i] > 0 else np.nan

        rows.append({
            "Năm": nam,
            "Sản lượng (kWh)": prod[i],
            "Doanh thu (VNĐ)": rev[i],
            "Chi phí OPEX (VNĐ)": opex[i],
            "EBITDA (VNĐ)": ebitda_l[i],
            "Khấu hao (VNĐ)": deprec_l[i],
            "Lãi vay (VNĐ)": interest_l[i],
            "Thuế TNDN (VNĐ)": tax_eq[i],
            "Trả Gốc + Lãi (VNĐ)": service_l[i],
            "Chi đầu tư Inverter (VNĐ)": capex_inv_l[i],
            "DSCR": dscr,
            "Dòng tiền Equity (VNĐ)": cf_e,
            "Dòng tiền tích lũy (VNĐ)": tich_luy,
        })

    df = pd.DataFrame(rows)
    try:
        irr_p = npf.irr(cfs_project) * 100
    except Exception:
        irr_p = np.nan
    try:
        irr_e = npf.irr(cfs_equity) * 100
    except Exception:
        irr_e = np.nan
    return {
        "df": df, "capex": capex, "von_tu_co": von_tu_co, "von_vay": von_vay,
        "irr_project": irr_p, "irr_equity": irr_e,
        "npv_project": npf.npv(wacc_rate / 100, cfs_project),
        "npv_equity": npf.npv(wacc_rate / 100, cfs_equity),
        "hoan_von": hoan_von, "am_lai": am_lai,
        "min_dscr": df["DSCR"].dropna().min() if df["DSCR"].notna().any() else np.nan,
    }


def fmt_pct(x):
    return "Không xác định" if (x is None or np.isnan(x)) else f"{x:.2f}%"


res = run_model(suat_dau_tu)
df_finance = res["df"]

# =====================================================================
# 5. GIAO DIEN TABS
# =====================================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "Thẩm Định Tài Chính", "Đồ Thị & Độ Nhạy", "Chiến Lược Phát Triển", "Rủi Ro & Khắc Phục"])

with tab1:
    st.subheader("Chỉ số tài chính dự án")
    c1, c2, c3, c4 = st.columns(4)
    cards = [
        (c1, "IRR Dự án (Unlevered)", fmt_pct(res["irr_project"]), "#1E3A8A"),
        (c2, "IRR Vốn chủ (Levered)", fmt_pct(res["irr_equity"]), "#16A34A"),
        (c3, f"NPV Vốn chủ (chiết khấu {wacc_rate}%)", f"{res['npv_equity']:,.0f} VNĐ", "#D97706"),
        (c4, "Hoàn vốn tích lũy (nội suy)", res["hoan_von"], "#DC2626"),
    ]
    for col, title, val, color in cards:
        with col:
            st.markdown(
                f"<div class='metric-card'><b>{title}:</b><br>"
                f"<span style='font-size:1.3rem; color:{color}; font-weight:bold;'>{val}</span></div>",
                unsafe_allow_html=True)

    c5, c6, c7, c8 = st.columns(4)
    cards2 = [
        (c5, "Tổng mức CAPEX", f"{res['capex']:,.0f} VNĐ", "#1E3A8A"),
        (c6, "Vốn tự có (Equity)", f"{res['von_tu_co']:,.0f} VNĐ", "#16A34A"),
        (c7, "Vốn vay ngân hàng", f"{res['von_vay']:,.0f} VNĐ", "#D97706"),
        (c8, "NPV Dự án", f"{res['npv_project']:,.0f} VNĐ", "#1E3A8A"),
    ]
    st.write("")
    for col, title, val, color in cards2:
        with col:
            st.markdown(
                f"<div class='metric-card'><b>{title}:</b><br>"
                f"<span style='font-size:1.2rem; color:{color}; font-weight:bold;'>{val}</span></div>",
                unsafe_allow_html=True)
    st.write("")

    if not np.isnan(res["min_dscr"]):
        msg = (f"DSCR thấp nhất của dự án: {res['min_dscr']:.2f}. "
               "Ngân hàng thường yêu cầu DSCR tối thiểu từ 1,2 đến 1,3.")
        if res["min_dscr"] < 1.2:
            st.warning(msg + " Dự án đang thấp hơn ngưỡng, cần giảm tỷ lệ vay hoặc kéo dài kỳ hạn.")
        else:
            st.info(msg)
    if res["am_lai"]:
        st.warning("Dòng tiền tích lũy đã hoàn vốn nhưng sau đó âm trở lại (thường do chi phí thay Inverter). "
                   "Cần xem kỹ bảng dòng tiền.")
    if np.isnan(res["irr_equity"]) or np.isnan(res["irr_project"]):
        st.warning("IRR không xác định do dòng tiền không đổi dấu. Kiểm tra lại giá bán điện hoặc suất đầu tư.")

    st.markdown("### Mô hình dòng tiền chi tiết")
    df_display = df_finance.copy()
    for col in df_display.columns:
        if col == "Năm":
            continue
        if col == "DSCR":
            df_display[col] = df_display[col].map(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")
        else:
            df_display[col] = df_display[col].map("{:,.0f}".format)
    st.dataframe(df_display, width="stretch", height=450)

    csv = df_finance.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Tải bảng dòng tiền (CSV)", csv, "dong_tien_solar.csv", "text/csv")

with tab2:
    st.subheader("Biểu đồ xu hướng & phân tích độ nhạy")

    fig = go.Figure()
    fig.add_trace(go.Bar(x=df_finance["Năm"], y=df_finance["Dòng tiền Equity (VNĐ)"],
                         name="Dòng tiền ròng chủ đầu tư", marker_color="#10B981"))
    fig.add_trace(go.Scatter(x=df_finance["Năm"], y=df_finance["Dòng tiền tích lũy (VNĐ)"],
                             name="Dòng tiền tích lũy", line=dict(color="#EF4444", width=3), yaxis="y2"))
    fig.update_layout(
        xaxis=dict(title="Năm vận hành"),
        yaxis=dict(title="Dòng tiền ròng (VNĐ)", side="left"),
        yaxis2=dict(title="Tích lũy (VNĐ)", side="right", overlaying="y", showgrid=False),
        legend=dict(x=0.01, y=0.99), template="plotly_white")
    st.plotly_chart(fig, width="stretch")

    fig2 = go.Figure()
    fig2.add_trace(go.Bar(x=df_finance["Năm"], y=df_finance["Doanh thu (VNĐ)"], name="Doanh thu", marker_color="#3B82F6"))
    fig2.add_trace(go.Bar(x=df_finance["Năm"], y=df_finance["Chi phí OPEX (VNĐ)"], name="OPEX", marker_color="#F59E0B"))
    fig2.add_trace(go.Bar(x=df_finance["Năm"], y=df_finance["Trả Gốc + Lãi (VNĐ)"], name="Trả nợ", marker_color="#6B7280"))
    fig2.update_layout(barmode="group", template="plotly_white", xaxis_title="Năm vận hành",
                       yaxis_title="VNĐ", legend=dict(x=0.01, y=0.99))
    st.plotly_chart(fig2, width="stretch")

    st.markdown("### Độ nhạy IRR vốn chủ theo giá bán điện và suất đầu tư")
    price_steps = [0.8, 0.9, 1.0, 1.1, 1.2]
    suat_steps = [0.9, 0.95, 1.0, 1.05, 1.1]
    z, txt = [], []
    for pm in price_steps:
        row, trow = [], []
        for sm in suat_steps:
            v = run_model(suat_dau_tu * sm, pm)["irr_equity"]
            row.append(None if np.isnan(v) else v)
            trow.append("N/A" if np.isnan(v) else f"{v:.1f}%")
        z.append(row)
        txt.append(trow)
    heat = go.Figure(go.Heatmap(
        z=z, x=[f"{suat_dau_tu * s:.1f} tr/kWp" for s in suat_steps],
        y=[f"Giá {int((p - 1) * 100):+d}%" for p in price_steps],
        text=txt, texttemplate="%{text}", colorscale="RdYlGn", colorbar=dict(title="IRR %")))
    heat.update_layout(template="plotly_white", xaxis_title="Suất đầu tư", yaxis_title="Biến động giá bán điện")
    st.plotly_chart(heat, width="stretch")

    st.markdown("### Độ nhạy DSCR thấp nhất theo tỷ lệ vay")
    st.caption("Tính theo các tham số hiện tại, chỉ thay tỷ lệ vay trong bảng này.")
    st.write("Để xem DSCR theo tỷ lệ vay khác nhau, chỉnh thanh trượt tỷ lệ vốn vay ở bên trái.")

with tab3:
    st.subheader("Giải pháp chiến lược tăng trưởng")
    strategies = [
        ("1. Tài chính & Huy động vốn", [
            ("Hợp vốn tài chính (Syndicated Funding)",
             "Liên kết quỹ đầu tư xanh quốc tế hoặc định chế như IFC, ADB để có kỳ hạn vay 10 đến 12 năm, "
             "lãi suất ưu đãi, cải thiện DSCR và rút ngắn hoàn vốn vốn tự có."),
            ("Chứng chỉ I-REC và tín chỉ carbon",
             "Đưa điều khoản sở hữu chứng chỉ I-REC vào hợp đồng, gom bán cho doanh nghiệp có cam kết Net-Zero. "
             "Nguồn thu bổ sung ước tính 3 đến 5% doanh thu, không tốn chi phí vận hành."),
        ]),
        ("2. Thị trường & Mô hình sản phẩm", [
            ("Tích hợp lưu trữ năng lượng (BESS)",
             "Gói Solar + BESS tích điện giờ thấp điểm, phát giờ cao điểm cho nhà xưởng, "
             "tăng biên lợi nhuận nhờ chênh lệch giá cao điểm của EVN."),
            ("Bán chéo dịch vụ O&M",
             "Nhận vận hành, bảo dưỡng cho hệ thống của khách hàng khác, "
             "tận dụng đội kỹ thuật sẵn có để tăng doanh thu ổn định."),
        ]),
        ("3. Vận hành & Công nghệ", [
            ("Giám sát từ xa và bảo trì dự đoán",
             "Dùng hệ thống giám sát thông minh phát hiện sớm suy hao, bụi bẩn, lỗi inverter, "
             "giữ sản lượng đúng cam kết hợp đồng PPA."),
            ("Hợp đồng dài hạn và điều khoản bảo vệ",
             "Ký hợp đồng 15 đến 25 năm, có điều khoản trượt giá, phạt chấm dứt sớm, "
             "chuyển nhượng hệ thống khi khách hàng đổi chủ."),
        ]),
    ]
    for header, items in strategies:
        st.markdown(f"### {header}")
        cols = st.columns(len(items))
        for col, (title, body) in zip(cols, items):
            with col:
                st.markdown(f"<div class='strat-card'><b>{title}</b><br>{body}</div>", unsafe_allow_html=True)

with tab4:
    st.subheader("Rủi ro & Khắc phục")
    risks = [
        ("Rủi ro chính sách giá điện",
         "Biểu giá EVN, cơ chế DPPA và quy định điện mặt trời mái nhà tự sản tự tiêu có thể thay đổi, "
         "làm giảm giá bán PPA.",
         "Thêm điều khoản điều chỉnh giá trong hợp đồng, kiểm tra độ nhạy giá ở tab Độ Nhạy."),
        ("Rủi ro tín dụng khách hàng",
         "Khách hàng nhà xưởng chậm thanh toán hoặc phá sản trong thời hạn hợp đồng.",
         "Thẩm định tài chính khách hàng, yêu cầu đặt cọc hoặc bảo lãnh, bảo hiểm tín dụng thương mại."),
        ("Rủi ro sản lượng và thiết bị",
         "Bức xạ thực tế thấp hơn dự báo, suy hao nhanh, inverter hỏng sớm.",
         "Dùng thiết bị tier 1 có bảo hành, hợp đồng O&M có cam kết hiệu suất (PR), mua bảo hiểm tài sản."),
        ("Rủi ro lãi suất và đòn bẩy",
         "Lãi suất thả nổi tăng làm DSCR giảm dưới ngưỡng ngân hàng yêu cầu.",
         "Cố định lãi suất giai đoạn đầu, giữ DSCR tối thiểu từ 1,3, thương lượng kỳ hạn dài hơn."),
        ("Rủi ro thuế và ưu đãi",
         "Điều kiện hưởng ưu đãi thuế TNDN và chuyển lỗ có thể khác với giả định trong mô hình.",
         "Đối chiếu quy định hiện hành với kế toán và tư vấn thuế trước khi đưa vào hồ sơ vay."),
        ("Rủi ro mái nhà và quyền sử dụng",
         "Mái yếu, nhà xưởng chuyển nhượng hoặc hết hạn thuê đất trước thời hạn hợp đồng.",
         "Khảo sát kết cấu mái, đăng ký quyền sử dụng mái bằng hợp đồng có công chứng."),
    ]
    cols = st.columns(2)
    for i, (title, desc, fix) in enumerate(risks):
        with cols[i % 2]:
            st.markdown(
                f"<div class='risk-card'><b>{title}</b><br>{desc}<br><br><b>Khắc phục:</b> {fix}</div>",
                unsafe_allow_html=True)

    st.caption("Mô hình mang tính tham khảo, cần xác nhận số liệu thực tế với nhà cung cấp, ngân hàng và tư vấn thuế.")
