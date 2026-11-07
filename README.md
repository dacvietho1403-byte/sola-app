# sola-app
MÔ HÌNH TÀI CHÍNH SOLA

## Hệ thống Multi-Agent (LangGraph)

Thư mục `agents/` chạy quy trình từ lead đến vận hành trên LangGraph, có các bước duyệt của người thật và lưu trạng thái ra SQLite (tắt chương trình rồi duyệt tiếp được).

### Luồng xử lý

| Bước | Agent / Người duyệt | Điều kiện đi tiếp |
|---|---|---|
| 1 | AI-03 Nội dung Marketing | Có chiến dịch thì lập kế hoạch nội dung |
| 2 | AI-04 Lọc lead (chấm 4 tiêu chí, ngưỡng 60 điểm) | Đạt chuẩn, đủ dữ liệu |
| 3 | AI-05 Đặt lịch khảo sát | |
| 4 | **TP QLKT** xác nhận khảo sát, nhập kWp thực tế | Mái đủ điều kiện |
| 5 | AI-06 Báo giá (giá vốn, markup, VAT, cảnh báo vượt ngân sách) | |
| 6 | **TP Thị trường / Giám đốc** duyệt báo giá | Duyệt, hoặc yêu cầu lập lại với markup mới (tối đa 3 lần) |
| 7 | AI-13 Hợp đồng (lịch thanh toán 30/65/5, kiểm tra pháp lý) | Báo giá đã APPROVED |
| 8 | **Giám đốc** ký hợp đồng | |
| 9 | AI-11 Hóa đơn tạm ứng 30% | Hợp đồng SIGNED |
| 10 | AI-07 Thi công | |
| 11 | **TP QLKT** nghiệm thu | Không đạt thì quay lại khắc phục (tối đa 3 lần) |
| 12 | AI-11 Hóa đơn nghiệm thu 65% và lịch thu 5% bảo hành | Đã nghiệm thu |
| 13 | AI-10 Báo cáo dòng tiền dự án | |
| 14 | **Kế toán trưởng** duyệt | |
| 15 | AI-02 IRR, thời gian hoàn vốn phía khách hàng | |
| 16 | AI-01 Báo cáo Giám đốc | |

Vận hành (`agents/om.py`): AI-08 so sản lượng thực tế với kỳ vọng (kWp × 1.450 kWh/kWp/năm). Dưới 85% thì AI-09 mở ticket sự cố, SLA 4 giờ nếu dưới 60%, 24 giờ nếu từ 60 đến 85%.

Kiểm soát:
- Mỗi bước duyệt kiểm tra vai trò. AI Agent không được duyệt. Quyết định sai quyền bị từ chối, ghi log ngay và hỏi lại.
- Mỗi agent tự kiểm tra điều kiện tiên quyết (`GateError`), không chỉ dựa vào cạnh của graph.
- Audit log có thời gian, người thực hiện, vai trò.
- Tiền tính bằng đồng (int), làm tròn bằng Decimal. Mã chứng từ dạng `PREFIX-YYYYMMDD-XXXXXX`, không trùng.

### Cài đặt và chạy

```bash
pip install -r requirements-agents.txt
python -m agents.cli demo                       # chạy thử toàn bộ với quyết định mẫu

python -m agents.cli start  --thread HS-001 --lead examples/lead_abc.json --campaign "Năng lượng Xanh Q4"
python -m agents.cli status --thread HS-001
python -m agents.cli decide --thread HS-001 --role TECH_HEAD --user "Nguyễn Văn A" --approve --capacity 160
python -m agents.cli decide --thread HS-001 --role MARKETING_HEAD --user "Trần B" --reject --revise-margin 0.12
python -m agents.cli decide --thread HS-001 --role TECH_HEAD --user "Nguyễn Văn A" --reject --defect "Thiếu tiếp địa"
python -m agents.cli log    --thread HS-001
python -m agents.cli monitor --thread HS-001 --kwh 18000 --period 11/2026

python -m pytest -q
```

Vai trò: `TECH_HEAD`, `MARKETING_HEAD`, `DIRECTOR`, `CHIEF_ACCOUNTANT`.

### Tham số

Sửa trong `agents/config.py` hoặc đặt biến môi trường `SOLA_<TÊN>`, ví dụ `SOLA_VAT_RATE=0.08`, `SOLA_UNIT_COST_PER_KWP=11500000`, `SOLA_SELLER_TAX_CODE=...`, `SOLA_DB_PATH=...`.

### Giới hạn hiện tại

- Các agent chạy theo quy tắc nghiệp vụ, chưa gọi LLM.
- Hóa đơn chỉ ở trạng thái `READY_TO_ISSUE`, chưa kết nối nhà cung cấp hóa đơn điện tử.
- Sản lượng nhập tay qua lệnh `monitor`, chưa đọc từ IoT/inverter.
