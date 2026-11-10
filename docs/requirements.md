# REQUIREMENTS: BOM Management Web Tool

Phiên bản: 0.1 (draft)
Trạng thái: chờ người dùng trả lời các câu hỏi mở ở mục 9 trước khi chốt.

Lưu ý nguồn dữ liệu: bản draft này được viết từ brief và các quan sát đã xác nhận từ dump Excel (VF3 FL FRS 3B.1.11.0 V8, VF3 Legacy FRS 3A.1.11.0 V6, EBUS BG.1.9.4). Các file sample gốc nằm trên máy của người dùng nên chưa được đối chiếu trực tiếp trong phiên viết tài liệu này. Mọi chi tiết cột/hàng cần được xác nhận lại khi viết parser.

## 1. Mục tiêu

Một web tool chạy LOCAL để kiểm soát HW/SW BOM (part number) theo FRS cho các dự án xe VinFast E/E (VF3, ECVan, EBUS...). Dữ liệu nguồn là các file Excel BOM đã có trong thư mục database trên OneDrive. Tool đọc, chuẩn hóa, lập chỉ mục và cho phép truy xuất, so sánh, xem cây FRS.

## 2. Người dùng và phạm vi

- Người dùng: PM và kỹ sư E/E, nhiều người có thể mở cùng lúc, dữ liệu nằm trên OneDrive share.
- Chạy trên máy cá nhân (Windows, Python 3.13), không cần server trung tâm.
- Ngoài phạm vi (v1): chỉnh sửa BOM từ release note (đã có BOM_autofill_dev), gọi REST Jira TMS (bị chặn), phân quyền người dùng.

## 3. Mô hình dữ liệu (khái niệm)

```
Project (VF3, ECVan, EBUS)
  Line (cây, tự tham chiếu parent)       vd VF3 Legacy -> VF3 Legacy LHD / RHD
    FRS (mã FRS, vd 3B.1.11.0)
      TPV release (TPV1..TPVn == V1..Vn), mỗi TPV gắn 1 file BOM
        ECU block (ECU + variant theo market/supplier + applicability)
          Part row (PN Type, DID, VF PN, Rev, Purchase PN...)
      Change content (theo TPV, ECU)  -> ticket CCB / Jira
      COM_BOM (ECU, PU PN, HW PN, SW PN, BL version, remark)
```

Quy ước:
- TPVn và Vn là cùng một khái niệm. File BOM V8 là BOM của TPV8 và chứa lịch sử change content TPV1..TPV8.
- Mã FRS: `[prefix.]seg.major.minor`, regex `(?:[A-Z]{1,3}\.)?\d+\.\d+\.\d+`. Ký tự đầu của VF3 là `3`, chữ kế tiếp là thế hệ (A Legacy, B Facelift), segment giữa mã hóa LHD/RHD/khu vực (1 LHD, 6 RHD, 8 in-region PHL, cần xác nhận).

## 4. Yêu cầu chức năng

### 4.1 Dashboard dự án và line xe
- FR-01: Dashboard liệt kê các dự án, chọn dự án để vào trang chi tiết.
- FR-02: Thêm dự án mới (tên, mô tả, thư mục database).
- FR-03: Mỗi dự án có cây line xe nhiều cấp (line cha, line con). Thêm, đổi tên, di chuyển, xóa line.
- FR-04: Dự án không có line vẫn hợp lệ (FRS gắn thẳng vào dự án).

### 4.2 FRS và import
- FR-05: Mỗi line có danh sách FRS. Tạo FRS mới (nhập tay) hoặc import từ file Excel.
- FR-06: Import tự detect: mã FRS và TPV từ tên file và title sheet, sheet BOM chính, hàng header, vị trí các cột theo TEXT header (không hard-code chỉ số cột), các cột applicability theo market/variant.
- FR-07: Hỗ trợ ít nhất 2 template: HWSW BOM VF3 (có cột "Purchase Partnumber before Reflashing") và template EBUS (không có cột đó, có `Flash Driver`, cột `VSR COMMENTS`).
- FR-08: Parser dừng khi gặp N hàng trống liên tiếp (sheet có thể có hơn 1 triệu hàng định dạng). Tham chiếu: `EMPTY_STREAK_STOP=50` của `frs_parser.py`.
- FR-09: Có thể quét cả thư mục database để import hàng loạt, hiển thị bản xem trước (preview) trước khi ghi, báo file lỗi hoặc bị bỏ qua.
- FR-10: Re-import file đã có (cùng FRS + TPV) thì cập nhật và hiển thị diff so với lần trước.

### 4.3 ECU và part
- FR-11: Mỗi ECU hiển thị các dòng PN Type: HW, SW, BootLoader, SW_BASIC, SW_APP, CAL, FL DRV, XML, FONT, HMI, TBOX... kèm DID, VF PN, Rev, Purchase Level, Purchase PN, Remarks.
- FR-12: Một ECU có thể có nhiều block (variant theo market/supplier: MHU, BMS, 2IN1, ABS, BCM...). Tool giữ nhãn variant và tập applicability (X = áp dụng, O = không áp dụng) theo từng cột market.
- FR-13: Chuẩn hóa tên ECU (alias): cột A "Common ECU Name" là tên chuẩn; ánh xạ các biến thể tên (CVCLW và VCU, BootLoader và BL, `2in1` và `2IN1`, `BCM ` có trailing space, `BMS (CKD)`...). Alias do người dùng chỉnh được.
- FR-14: Cột merge theo block (Purchase PN, Remarks) được đọc đúng: giá trị gắn cho cả block, không gán nhầm cho hàng đầu.

### 4.4 Change content
- FR-15: Đọc sheet `Change content ` (có trailing space) và detect hàng header (có file ở row 1, có file ở row 2 sau title).
- FR-16: Lưu theo (TPV, ECU, nội dung, remarks). TPV merge dọc gom nhiều ECU.
- FR-17: Trích xuất ticket bằng regex: `CCB-\d+`, `VF3-\d+`, `VF3RHD-\d+`, `MINIOGREEN-\d+`, `GTSC-\d+`. Hiển thị là link `https://tms.vinfast.vn/browse/<KEY>`.
- FR-18: Nhận diện ghi chú dạng "Carry over from...", "Carry-across from FRS x TPVn", "No new SW update, only new CCB" và lưu thành quan hệ/nhãn.
- FR-19: Xuất change content theo FRS, theo khoảng TPV, hoặc theo ECU ra Excel/CSV.

### 4.5 Truy xuất
- FR-20: Tìm theo tên/mã FRS: trả về các ECU, variant và toàn bộ PN của FRS đó.
- FR-21: Tìm theo part number: trả về ECU, PN Type, FRS, TPV, line đang dùng PN đó (where-used).
- FR-22: Chuẩn hóa PN khi so khớp: bỏ khoảng trắng đầu/cuối, khoảng trắng chen giữa, phân biệt PN có revision và không có revision (PU PN và HW PN trong COM_BOM). Tìm gần đúng (prefix, bỏ revision).
- FR-23: Lọc theo dự án, line, market, ECU, PN Type, khoảng TPV.
- FR-24: So sánh hai FRS/TPV (diff BOM theo ECU và PN Type).

### 4.6 COM_BOM (Compatible BOM)
- FR-25: Đọc sheet `COM_BOM` ("Compatibility Matrix - Hardware to Software"): ECU, PU PN, HW PN, SW PN, BL Version, Remark. Xử lý ô merge dọc: ECU merge nhiều hàng, một SW PN merge qua nhiều HW PN nghĩa là SW tương thích với tất cả các HW đó.
- FR-26: Truy vấn tương thích: cho (ECU, SW PN) trả về các HW PN tương thích, và ngược lại. Hiển thị ma trận HW x SW.
- FR-27: Cảnh báo khi BOM của một FRS có cặp HW + SW không nằm trong COM_BOM.
- FR-28: Ánh xạ PU PN (không rev) với HW PN (có rev) và tên ECU có hậu tố variant (`MHU VN`, `BCM PHL`, `BMS (FBU)`, `2IN1 (PHL)`).

### 4.7 Sơ đồ cây FRS
- FR-29: Dashboard hiển thị cây: Project, Line, FRS, TPV; mở rộng/thu gọn, zoom.
- FR-30: Hiển thị nhánh quan hệ giữa các FRS (kế thừa, carry-across, base cho FOTA như sheet `FRS 3B.1.7.0 BOM (for FOTA)`). Nguồn quan hệ: tự suy ra từ change content/sheet FOTA và cho phép người dùng sửa tay.
- FR-31: Click một nút để mở chi tiết FRS/TPV, ECU, change content.

### 4.8 Sheet Data
- FR-32: Đọc sheet `Data` làm danh mục tham chiếu: PN Type, Carry Over Information, CAN DBC version, SW Update Compatibility (FOTA Only, FOTA+OBD, FOTA+USB, FOTA+Bench (VF), OBD Only, Bench Only (VF), Supplier Only).

### 4.9 Chất lượng dữ liệu
- FR-33: Chuẩn hóa khi đọc (strip, gộp khoảng trắng) nhưng GIỮ giá trị gốc để đối chiếu.
- FR-34: Báo cáo data quality cho mỗi lần import: PN gãy (`SOW690740 03AA-01`), PN cụt (`EEP69081000A`), `#VALUE!`, thiếu Rev, khác biệt giữa BOM và COM_BOM. Có trang xem và export danh sách cảnh báo.
- FR-35: Không sửa file Excel gốc. Tool chỉ đọc.

## 5. Yêu cầu phi chức năng

- NFR-01: Chạy local, Python stdlib ưu tiên (`http.server`, `sqlite3`), `openpyxl` cho Excel. Không dùng fastapi/flask/pandas/sqlalchemy. Frontend HTML + JS thuần.
- NFR-02: Cổng mặc định khác 8000 (Abbreviation Web đã dùng), đề xuất 8010, tự tìm cổng trống nếu bận.
- NFR-03: Khởi chạy theo convention: `.vbs` -> `.bat` -> `Tools\_shared\startup_loader.py --launch-mode web --wait-url http://127.0.0.1:<port>/`. Có `.vbs` để đăng ký vào `POWER_TOOLS` của FRS_Management.
- NFR-04: Cấu trúc thư mục: `_func/`, `_input/`, `_output/`, `assets/`, `feature/`.
- NFR-05: Chịu được OneDrive: nhiều người mở cùng lúc, không khóa file Excel (mở read-only, copy tạm khi cần), không để SQLite DB chạy trực tiếp trên thư mục đồng bộ (xem plan, mục kiến trúc dữ liệu).
- NFR-06: Import một file BOM điển hình dưới vài giây; quét cả thư mục có tiến trình.
- NFR-07: Giao diện tiếng Việt, thuật ngữ kỹ thuật tiếng Anh.
- NFR-08: Có chỗ tích hợp (hook) cho BOM_autofill_dev, chưa cần làm trong v1.

## 6. Quy tắc parser (tóm tắt)

- Chọn sheet BOM chính bằng header chứa `COMMON ECU NAME` (tham chiếu `select_bom_sheet`).
- Header ở row 3, dữ liệu từ row 4 (`DATA_START_ROW=4`), nhưng phải detect, không tin vị trí cố định.
- Cột: A Common ECU Name, B PN Type, C VF PN with Revision, D Component name as per system, E PN Type, F DID No, G VF PN, H Rev DID, I Rev, J Purchase Level, K Purchase Part Number with Rev, L before Reflashing, M after Reflashing, N Purchase Remarks, O.. cột applicability, cuối là Remarks / Change Content.
- DID: HW = F191/F141, SW = F188/F148, BootLoader = F101 (không có rev, giá trị hex 4 ký tự), SW_BASIC = F105/F145, SW_APP = F104/F144, CAL = F102/F142. Purchase Level = `D`.
- Purchase PN gắn với HW của block.
- Row 2 có thể chứa tên market (`VN`, `PHL`, `LAOS`) ở các cột applicability; row 3 chứa tên variant (`VN FL`, `VN BCO2`, `Base`).

## 7. Tiêu chí chấp nhận (v1)

- AC-01: Import đúng 3 file mẫu, số ECU/block/part khớp đếm tay ở ít nhất 3 ECU mỗi file.
- AC-02: Tìm một PN bất kỳ trong file mẫu trả về đúng ECU và FRS, kể cả khi PN có khoảng trắng thừa.
- AC-03: Truy vấn COM_BOM trả đúng danh sách HW cho một SW có ô merge dọc.
- AC-04: Change content của FRS 3B.1.11.0 trích ra đủ TPV1..TPV8, ticket thành link.
- AC-05: Cây FRS hiển thị ít nhất Project, Line, FRS, TPV cho VF3.
- AC-06: Hai người mở tool cùng lúc trên OneDrive không làm hỏng dữ liệu.

## 8. Rủi ro

- Template giữa các dự án khác nhau (VF3 so với EBUS), thêm template mới thường xuyên.
- Dữ liệu bẩn (PN gãy, thiếu Rev, `#VALUE!`).
- OneDrive: sync conflict, file lock, người dùng sửa Excel trong lúc tool đang đọc.
- Quan hệ giữa các FRS (cây nhánh) không có nguồn dữ liệu rõ ràng, có thể phải nhập tay.
- Ý nghĩa segment giữa của mã FRS (1, 6, 8) chưa chắc chắn.

## 9. Câu hỏi mở (cần người dùng trả lời)

Dữ liệu và import
1. Khi cùng một FRS có nhiều file BOM (V6, V7, V8), mỗi file là một TPV độc lập, hay chỉ cần giữ file mới nhất (chứa lịch sử change content)? Có cần xem BOM của từng TPV cũ không?
2. Sheet `FRS 3B.1.7.0 BOM (for FOTA)` là snapshot BOM của FRS khác: nên coi là nút cha (base) của FRS hiện tại trong cây, đúng không? Còn nguồn nào khác để biết quan hệ cha-con giữa các FRS?
3. Segment giữa của mã FRS (1, 6, 8) có đúng nghĩa 1 = LHD, 6 = RHD, 8 = in-region PHL không? Có bảng quy ước chính thức không?
4. Một FRS có thể thuộc nhiều line cùng lúc không (vd FRS dùng chung LHD và RHD)?
5. Mỗi cột applicability (VN FL, VN BCO2, PHL BCO...) có phải là một "variant xe" cần thành thực thể riêng để lọc không, hay chỉ là nhãn hiển thị?
6. Template EBUS khác VF3 ở những cột nào ngoài "before Reflashing" và `VSR COMMENTS`? Có thêm template nào sắp tới không (ECVan)?

Nghiệp vụ
7. Khi hai block của cùng ECU có cùng PN nhưng khác applicability, có coi là cùng một "ECU config" không?
8. COM_BOM: "tương thích" chỉ có hai trạng thái (có trong bảng = tương thích, không có = không tương thích), hay cần thêm trạng thái "chưa xác nhận", "tương thích có điều kiện" (Remark)?
9. Cảnh báo cặp HW+SW ngoài COM_BOM: chỉ cảnh báo hay chặn?
10. Tool có cần cho phép chỉnh sửa/nhập tay dữ liệu (vd thêm FRS, sửa PN), hay chỉ đọc từ Excel và Excel luôn là nguồn sự thật?
11. Cần so sánh (diff) hai FRS theo cách nào là quan trọng nhất: cùng line khác TPV, khác line cùng nền, hay Legacy so với Facelift?
12. Danh sách alias tên ECU (CVCLW/VCU...) đã có sẵn ở đâu, hay tool tự gợi ý và người dùng duyệt?

Vận hành
13. Thư mục database cuối cùng sẽ tổ chức thế nào (theo folder dự án/line như `FRS_Management\_input\{6M,8M,...}` hay phẳng như thư mục `sample`)? Tool nên suy ra line từ cấu trúc folder hay từ tên file?
14. Có bao nhiêu người dùng đồng thời và bao nhiêu file BOM (ước lượng 100, 1000, hơn)? Điều này quyết định có cần chỉ mục SQLite hay chỉ cần đọc trực tiếp.
15. Có cần xuất báo cáo (Excel/PDF) nào cố định cho họp release không?
16. Có cần link ngược từ ticket sang các FRS/ECU (tìm theo `CCB-xxxxx`) không?
