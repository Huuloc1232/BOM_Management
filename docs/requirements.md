# REQUIREMENTS: BOM Management Web Tool

Phiên bản: 0.3 (draft, đã đối chiếu với `docs/sample.xlsx`)
Trạng thái: còn một số câu hỏi nhỏ ở mục 10, không chặn việc bắt đầu Giai đoạn 1.

Lưu ý nguồn dữ liệu: mục 7 (quy tắc parser) đã được đối chiếu trực tiếp với `docs/sample.xlsx` (VF3 FRS 3B.1.11.0 V8), là **template chuẩn cho tất cả dự án**. Các quan sát về file VF3 Legacy 3A.1.11.0 và EBUS trong brief ban đầu không còn là căn cứ thiết kế (mọi dự án dùng cùng một template).

## 1. Mục tiêu

Web tool chạy LOCAL cho một người dùng, để **truy xuất nhanh** HW/SW BOM (part number) theo FRS cho các dự án xe VinFast E/E (VF3, ECVan, EBUS...). Dữ liệu nguồn là các file Excel BOM trong thư mục database (OneDrive). Excel luôn là nguồn sự thật của BOM, tool chỉ đọc, lập chỉ mục, tra cứu, so sánh và vẽ cây FRS.

## 2. Phạm vi

- Một người dùng, dưới 100 file BOM hiện tại (số lượng có thể tăng, thiết kế không được chặn việc mở rộng).
- Chạy trên máy cá nhân (Windows, Python 3.13), không cần server trung tâm.
- Không xuất báo cáo cố định cho họp release (mục đích chính là truy xuất nhanh).
- Ngoài phạm vi v1: sửa BOM từ release note (đã có BOM_autofill_dev), gọi REST Jira TMS (bị chặn), phân quyền, chỉnh sửa PN/BOM trong tool.

## 3. Quyết định nghiệp vụ đã chốt

| # | Quyết định |
|---|---|
| D1 | Mỗi FRS chỉ cần **TPV cuối cùng** (V lớn nhất). File đó chứa toàn bộ thay đổi của các V trước và là thông tin chính thức của FRS. Các file V cũ không cần lưu BOM. |
| D2 | Quan hệ cha-con giữa các FRS suy ra từ mã FRS (mục 5.7), có thể tách nhánh, người dùng sửa tay được. |
| D3 | Segment giữa của mã FRS: `1` = LHD, `6` = RHD. Chưa có quy ước chính thức cho giá trị khác, dùng bảng ánh xạ cấu hình được. |
| D4 | Một FRS có thể thuộc nhiều line cùng lúc (vd hai line dùng hai biến thể pin). LHD và RHD là hai FRS khác nhau (khác segment), không dùng chung FRS. |
| D5 | Mỗi cột applicability (VN FL, VN BCO2, PHL BCO...) là một **variant xe**, là thực thể riêng để lọc. |
| D6 | Chỉ có **một template chuẩn** (`docs/sample.xlsx`) cho mọi dự án, gồm 3 sheet: BOM, `COM_BOM`, `Change content `. Không có template khác. Parser vẫn detect cột theo text header để chịu được việc thêm/bớt cột variant. |
| D7 | COM_BOM chỉ có hai trạng thái: tương thích hoặc không. Tương thích khi bộ ba (ECU, HW PN, SW PN) có trong bảng. Không có trong bảng, hoặc có HW đó nhưng đi với SW số khác, là không tương thích. COM_BOM chỉ liệt kê một số ECU (trong sample: MHU, SS, ACM, 2IN1, EAC); ECU không có trong COM_BOM là "không theo dõi", không phải "không tương thích". |
| D8 | Cặp HW+SW không có trong COM_BOM: chỉ **cảnh báo**, không chặn. |
| D9 | BOM, PN và mọi thông tin kèm theo chỉ đọc từ Excel. **FRS được phép tạo thêm trong tool** (gắn với line, gắn với file Excel) và truy xuất từ file Excel. |
| D10 | So sánh hai FRS tập trung vào **ECU part number** (HW, SW, BL, SW_BASIC, SW_APP, CAL...). |
| D11 | Alias tên ECU lấy từ chính file Excel (cột A là tên chuẩn, cột D là tên theo system, cột E có thể ghi `BL` thay vì `BootLoader`, tên ở COM_BOM và Change content có hậu tố variant). Tool tự ghép, cho người dùng duyệt các ghép nối không chắc chắn. |
| D12 | Database tổ chức **theo folder dự án**. Line xe suy ra từ **cả cấu trúc folder và tên file**; khi hai nguồn mâu thuẫn thì hiển thị để người dùng chọn. |
| D13 | Ticket (CCB, IMS, và các key Jira) có tra cứu ngược: ticket thuộc FRS/ECU nào, và FRS đã release những ticket nào. |

## 4. Mô hình dữ liệu (khái niệm)

```
Project (VF3, ECVan, EBUS)
  Line (cây, tự tham chiếu parent)       vd VF3 Legacy -> VF3 Legacy LHD / RHD
    FRS (mã FRS)  <-- nhiều-nhiều với Line (D4)
      TPV cuối (số V, file BOM)           chỉ giữ bản cuối (D1)
        Variant xe (cột applicability: VN FL, VN BCO2, PHL BCO...)   (D5)
        ECU block (ECU + nhãn variant ECU)
          Part row (PN Type, DID, VF PN, Rev, Purchase PN...)
      Change content (theo TPV con, ECU) -> ticket (CCB, IMS, VF3-, GTSC-...)
      COM_BOM (ECU, PU PN, HW PN, SW PN, BL version, remark)
  Quan hệ FRS cha-con (cây nhánh)
```

Quy ước:
- TPVn và Vn là cùng một khái niệm. File BOM V8 là BOM của TPV8 và chứa lịch sử change content TPV1..TPV8; change content vẫn giữ nhãn TPV con để truy được "thay đổi này vào ở TPV nào".
- Mã FRS lấy từ title ô A1 của sheet BOM (vd `FRS 3B.1.11.0 V8 LHD`: mã FRS, số V và LHD/RHD), từ tên sheet (`VF3 FRS 3B.1.11.0 BOM V8`) và từ A1 của sheet Change content. Đối chiếu ba nơi, lệch thì cảnh báo.
- Mã FRS: `[prefix.]seg.major.minor`, regex `(?:[A-Z]{1,3}\.)?\d+\.\d+\.\d+`. Với VF3 (`3B.1.8.0`): `3` là dòng xe, `B` là thế hệ (A Legacy, B Facelift), `1` segment (1 LHD, 6 RHD), `8` major, `0` minor.

## 5. Yêu cầu chức năng

### 5.1 Dashboard dự án và line xe
- FR-01: Dashboard liệt kê dự án, chọn dự án để vào trang chi tiết.
- FR-02: Thêm dự án mới (tên, thư mục database).
- FR-03: Mỗi dự án có cây line xe nhiều cấp (line cha, line con). Thêm, đổi tên, di chuyển, xóa line.
- FR-04: Dự án không có line vẫn hợp lệ (FRS gắn thẳng vào dự án).
- FR-05: Gán một FRS vào nhiều line (D4).

### 5.2 FRS, import và quét thư mục
- FR-06: Quét thư mục dự án, nhận diện file BOM, nhóm theo mã FRS, **chọn file V cao nhất** làm TPV cuối (D1). Hiển thị các V cũ bị bỏ qua.
- FR-07: Tạo FRS mới trong tool (D9): nhập mã FRS, gán line, gắn file Excel (có thể gắn sau). FRS chưa có file hiển thị trạng thái "chưa có BOM".
- FR-08: Import tự detect: mã FRS và số V từ tên file và title sheet, sheet BOM chính, hàng header, vị trí cột theo TEXT header, cột applicability (variant xe).
- FR-09: Hỗ trợ template chuẩn duy nhất (D6, mục 7). Parser detect cột theo text header (đã chuẩn hóa khoảng trắng và xuống dòng) và chịu được số cột variant thay đổi.
- FR-10: Parser dừng khi gặp N hàng trống liên tiếp (sheet có thể có hơn 1 triệu hàng định dạng). Tham chiếu `EMPTY_STREAK_STOP=50` của `frs_parser.py`.
- FR-11: Quét lại (rescan) theo thời gian sửa file/hash: chỉ parse lại file đổi. Khi xuất hiện V mới hơn của cùng FRS thì thay thế TPV cuối và hiển thị diff so với bản trước.
- FR-12: Line suy ra từ folder và tên file (D12); mâu thuẫn thì hiển thị để chọn.

### 5.3 ECU và part
- FR-13: Mỗi ECU hiển thị các dòng PN Type: HW, SW, BootLoader, SW_BASIC, SW_APP, CAL, FL DRV, XML, FONT, HMI, TBOX..., kèm DID, VF PN, Rev, Purchase Level, Purchase PN, Remarks.
- FR-14: Một ECU có thể có nhiều block (trong sample: MHU 2 block, BMS 3 block, 2IN1 2 block). Tool giữ các block riêng, gom dưới cùng một ECU, mỗi block kèm danh sách variant xe áp dụng (X) và không áp dụng (O), và nhãn block lấy từ cột Remarks (vd `VN FL: BMS (CKD)`, `VN with PTC`).
- FR-15: Chuẩn hóa tên ECU (alias) theo D11; hiển thị cả tên gốc.
- FR-16: Cột merge theo block (Purchase PN, Remarks) được đọc đúng: giá trị gắn cho cả block.

### 5.4 Change content và ticket
- FR-17: Đọc sheet `Change content ` (có trailing space), detect hàng header (có file ở row 1, có file ở row 2 sau title).
- FR-18: Lưu theo (TPV, ECU, nội dung, remarks); TPV merge dọc gom nhiều ECU.
- FR-19: Trích ticket theo **danh sách prefix cấu hình được**, không dùng regex chung `[A-Z]+-\d+` vì sẽ khớp nhầm part number (`SOW69011004AD-05`). Prefix ban đầu từ sample: `CCB`, `VF3`, `VF3RHD`, `VF5`, `GTSC`, `MINIOGREEN`, `MHU3`, thêm `IMS` (cần xác nhận, mục 10). Phải chịu được các dạng `[CCB-22560]`, `CCB-18815<tab>text`, `GTSC-7888]` (dấu ngoặc lệch), hai key liền nhau (`CCB-9228<tab>CCB-10245`). Hiển thị link `https://tms.vinfast.vn/browse/<KEY>` cho key Jira.
- FR-20: Tra cứu hai chiều (D13): nhập CCB/IMS thì ra FRS, TPV, ECU đã release; chọn FRS thì ra toàn bộ CCB/IMS của FRS đó (có lọc theo TPV).
- FR-21: Nhận diện ghi chú "Carry over from...", "Carry-across from FRS x TPVn", "No new SW update, only new CCB" và lưu thành nhãn/quan hệ.

### 5.5 Truy xuất (tính năng trọng tâm)
- FR-22: Một ô tìm kiếm toàn cục: gõ mã FRS, PN, tên ECU hoặc mã ticket đều ra kết quả phân nhóm, phản hồi dưới 1 giây.
- FR-23: Tìm theo FRS: trả về các ECU, variant và toàn bộ PN.
- FR-24: Tìm theo PN (where-used): trả về ECU, PN Type, FRS, line, variant xe đang dùng PN đó.
- FR-25: Chuẩn hóa PN khi khớp: bỏ khoảng trắng đầu/cuối và chen giữa; hỗ trợ tìm theo prefix và bỏ revision (PU PN không rev so với HW PN có rev).
- FR-26: Lọc theo dự án, line, variant xe, ECU, PN Type.
- FR-27: So sánh hai FRS theo ECU part number (D10): bảng ECU x PN Type, tô màu khác biệt, lọc "chỉ hiện khác biệt".

### 5.6 COM_BOM (Compatible BOM)
- FR-28: Đọc sheet `COM_BOM`: ECU, PU PN, HW PN, SW PN, BL Version, Remark. Xử lý ô merge dọc: ECU merge nhiều hàng; một SW PN merge qua nhiều HW PN nghĩa là SW tương thích tất cả các HW đó.
- FR-29: Truy vấn tương thích theo D7: cho (ECU, SW PN) trả danh sách HW tương thích và ngược lại; cho (ECU, HW, SW) trả "tương thích" hoặc "không tương thích" (ghi rõ lý do: không có HW trong bảng, hoặc HW đi với SW số khác).
- FR-30: Ma trận HW x SW cho từng ECU.
- FR-31: Cảnh báo (không chặn) khi BOM của một FRS có ECU **có trong COM_BOM** nhưng bộ ba (ECU, HW, SW) không nằm trong bảng (D8). ECU không có trong COM_BOM thì không cảnh báo. Trên sample: MHU block PHL BCO (HW `EEP69321001AC-01`, COM_BOM chỉ có `...AA-01`) và SS (HW `EEP69031001AE-02`, COM_BOM chỉ có `...AE-01`) sẽ bị cảnh báo.
- FR-32: Câu hỏi thường dùng: "SW mới nhất của ECU X có tương thích HW cũ không?" có nút trả lời nhanh.
- FR-33: Ánh xạ tên ECU trong COM_BOM có hậu tố market (`MHU VN`, `2IN1 (VN)`, `2IN1 (PHL)`) sang các block của BOM bằng market của variant xe (từ tiền tố nhãn variant: `VN FL` và `VN BCO2` là VN, `PHL BCO` là PHL). PU PN của COM_BOM nối với cột L (Purchase PN bỏ revision) của BOM, trong COM_BOM có dòng PU PN còn rev (`EEP69072000AD-01`), có dòng không.

### 5.7 Sơ đồ cây FRS
- FR-34: Dashboard hiển thị cây FRS theo line, mở rộng/thu gọn, zoom, click nút để mở chi tiết.
- FR-35: Quan hệ cha-con **suy ra tự động từ mã FRS** (trong cùng family và segment):
  - Minor > 0: cha là cùng major, minor - 1 (`3B.1.8.1` cha là `3B.1.8.0`; `3B.1.9.2` cha là `3B.1.9.1`).
  - Minor = 0: cha là major - 1, minor 0 (`3B.1.9.0` cha là `3B.1.8.0`).
  - Hệ quả: `3B.1.8.0` có hai con, `3B.1.9.0` (nhánh chính) và `3B.1.8.1` (nhánh phụ), đúng với ví dụ người dùng.
  - Khi FRS cha không có trong dữ liệu (chưa có file): nút cha hiển thị dạng "thiếu", hoặc nối lên tổ tiên gần nhất có sẵn.
- FR-36: Người dùng sửa tay cha-con (gán lại cha, tách nhánh) khi quy tắc suy ra sai. Quan hệ sửa tay luôn thắng quy tắc tự động.
- FR-37: Ghi chú "Carry over from FRS ..." / "Carry across SW from FRS ..." trong Change content (và sheet `... BOM (for FOTA)` nếu file có) dùng làm **gợi ý** đối chiếu với cây suy ra, cảnh báo khi mâu thuẫn. Các mã `FRS x.x.x Vn` nằm trong tiêu đề ticket là FRS nơi phát hiện lỗi, **không** dùng làm quan hệ cây.
- FR-38: Cây dùng được cho nhiều segment (LHD `3B.1.x` và RHD `3B.6.x` là hai cây/nhánh riêng, có thể bật/tắt).

### 5.8 Sheet Data
- FR-39 (tùy chọn): Sheet `Data` không có trong template chuẩn. Nếu file có sheet này thì đọc làm danh mục tham chiếu, nếu không có thì bỏ qua, không báo lỗi. Danh mục PN Type lấy từ chính dữ liệu cột B.

### 5.9 Chất lượng dữ liệu
- FR-40: Chuẩn hóa khi đọc (strip, gộp khoảng trắng) nhưng GIỮ giá trị gốc để đối chiếu.
- FR-41: Báo cáo data quality cho mỗi lần quét: PN gãy hoặc cụt, `#VALUE!`, thiếu Rev, khác biệt giữa BOM và COM_BOM, và các bất thường đã thấy trong sample: BootLoader lưu dạng số (`2422`, `1234`) làm mất số 0 đầu; ô DID gõ cứng `F101` thay vì công thức; cột E ghi `BL` còn cột B ghi `BootLoader`; ký tự trắng đầu chuỗi trong COM_BOM (`' EEP69081000AE'`); tên ECU có khoảng trắng cuối (`'BCM '`) hoặc khác hoa thường (`2in1`); dòng Change content có ECU nhưng nội dung trống. Trang xem được trong tool.
- FR-42: Không sửa file Excel gốc (D9).

## 6. Yêu cầu phi chức năng

- NFR-01: Python stdlib ưu tiên (`http.server`, `sqlite3`) + `openpyxl`. Không dùng fastapi/flask/pandas/sqlalchemy. Frontend HTML + JS thuần.
- NFR-02: Cổng mặc định khác 8000 (Abbreviation Web đã dùng), đề xuất 8010, tự tìm cổng trống nếu bận.
- NFR-03: Khởi chạy theo convention: `.vbs` -> `.bat` -> `Tools\_shared\startup_loader.py --launch-mode web --wait-url http://127.0.0.1:<port>/`. Có `.vbs` để đăng ký vào `POWER_TOOLS` của FRS_Management.
- NFR-04: Cấu trúc thư mục: `_func/`, `_input/`, `_output/`, `assets/`, `feature/`.
- NFR-05: Excel mở read-only, không khóa file người khác đang dùng; nếu Excel đang bị mở/khóa thì copy tạm rồi đọc. Một người dùng nên không cần cơ chế chống xung đột nhiều người, nhưng ghi metadata vẫn phải nguyên tử (ghi file tạm rồi đổi tên) để OneDrive sync không làm hỏng.
- NFR-06: Quét lần đầu dưới 100 file có tiến trình; quét lại chỉ parse file đổi; tìm kiếm dưới 1 giây.
- NFR-07: Giao diện tiếng Việt, thuật ngữ kỹ thuật tiếng Anh.
- NFR-08: Có chỗ tích hợp (hook) cho BOM_autofill_dev, chưa làm trong v1.
- NFR-09: Thiết kế chịu được tăng số file (hàng trăm đến nghìn) mà không đổi kiến trúc: chỉ mục SQLite và quét gia tăng.

## 7. Template chuẩn và quy tắc parser (đối chiếu với `docs/sample.xlsx`)

File có đúng 3 sheet. Tên sheet BOM thay đổi theo FRS/dự án (`VF3 FRS 3B.1.11.0 BOM V8`), nên chọn sheet BOM bằng nội dung (hàng header chứa `Common ECU Name`), không theo tên. Hai sheet còn lại có tên cố định `COM_BOM` và `Change content ` (có khoảng trắng cuối, so khớp sau khi trim).

### 7.1 Sheet BOM

Bố cục:
- `A1:C2` (merge): title `FRS 3B.1.11.0 V8 LHD` + xuống dòng + `HW SW BOM`. Nguồn chính cho mã FRS, số V, LHD/RHD.
- `D1:K1`: chú thích `X - Applicable / O - Not Applicable`. `D2:K2`: `For MBOM Team Reference`. Không có hàng market như brief ban đầu đoán.
- Hàng 3 là header, dữ liệu từ hàng 4 (sample: hàng 4 đến 52, sau đó trống). Sheet khai báo tới hơn 1 triệu hàng, nên dừng sau N hàng trống liên tiếp (`EMPTY_STREAK_STOP=50`).

| Cột | Header (đã chuẩn hóa) | Nội dung | Ghi chú cho parser |
|---|---|---|---|
| A | Common ECU Name | Tên ECU chuẩn, **lặp ở mọi hàng** (không merge) | Khóa gom ECU |
| B | PN Type | HW, SW, SW_BASIC, SW_APP, CAL, BootLoader | Giá trị chuẩn, dùng để phân loại hàng |
| C | VF PN with Revision | PN kèm rev (`EEP69080001AD-01`) hoặc mã BootLoader | BootLoader có thể là chuỗi `'0201'` hoặc **số** `2422`, `1234` (mất số 0 đầu): ép về chuỗi, pad 4 ký tự và báo cảnh báo |
| D | Component name as per system | Tên ECU theo system | Thường trùng A |
| E | PN Type | Lặp lại B | Có chỗ ghi `BL` thay vì `BootLoader`: coi `BL` là alias, lấy B làm chuẩn |
| F | DID No | **Công thức** suy từ B (`=IF(B4="HW","F191",...)`) | Một số ô gõ cứng `F101`. Tính lại DID từ B, không phụ thuộc công thức |
| G | VF PN | **Công thức** `=LEFT(C,FIND("-",C)-1)`; BootLoader `=C` | Tính từ C |
| H | Rev DID | Hằng: HW `F141`, SW `F148`, SW_BASIC `F145`, SW_APP `F144`, CAL `F142`; BootLoader để trống | |
| I | Rev | **Công thức** phần sau dấu `-`; BootLoader là `N/A` | Tính từ C |
| J | Purchase Level | `D` ở các dòng HW/SW/..., trống ở BootLoader | |
| K | Purchase Part Number with Rev | PU PN kèm rev, **merge theo block** (vd `K4:K6`, `K16:K21`) | Giá trị ở hàng đầu của block (hàng HW) |
| L | Purchase Partnumber before Reflashing | **Công thức** `=LEFT(K,13)` = PU PN bỏ rev, merge theo block | Khóa nối với cột `PU PN` của COM_BOM |
| M | Purchase Partnumber after Reflashing | Merge theo block, **trống trong sample** | Giữ chỗ cho PU PN sau khi reflash |
| N | Purchase Remarks | Merge theo block, trống trong sample | |
| O, P, Q... | Tên variant xe: `VN FL`, `VN BCO2`, `PHL BCO` | `X` hoặc `O` mỗi hàng | Số cột variant thay đổi: lấy mọi cột nằm giữa cột `Purchase Remarks` và cột `Remarks Change Content` |
| R | `Remarks\nChange Content` (header có xuống dòng) | Nhãn block, vd `VN FL: BMS (CKD)`, `VN with PTC`, `Phil non PTC`; merge theo block khi có | Chỉ có ở các ECU nhiều block |

Quy tắc:
- **Block**: bắt đầu tại mỗi hàng có `PN Type = HW`, kéo dài tới trước hàng HW kế tiếp. Khớp với các vùng merge của K, L, M, N. Một block có thể gồm `HW, SW, BootLoader` (đa số), `HW, SW, CAL, BootLoader` (ABS) hoặc `HW, SW_BASIC, SW, SW_APP, CAL, BootLoader` (CVCLW). Sample có 15 block của 11 ECU.
- Một ECU có thể có nhiều block: MHU 2 (VN FL + VN BCO2, và PHL BCO), BMS 3 (mỗi variant một block), 2IN1 2. Hai block cùng ECU có thể dùng **cùng HW PN** nhưng khác Purchase PN và khác SW (BMS `BAT69011016AA-01` ở block VN BCO2 và PHL BCO), hoặc cùng SW nhưng khác HW (2IN1 `SOW69272005AA-06`).
- Variant của block lấy từ hàng HW (các cột `X`). Kiểm tra mọi hàng của block có cùng mẫu X/O, lệch thì cảnh báo.
- Market của variant = tiền tố nhãn (`VN FL` và `VN BCO2` là VN, `PHL BCO` là PHL).
- Không tin cache của ô công thức: các cột F, G, I, L tính lại từ B, C, K; chỉ dùng giá trị cache để đối chiếu và cảnh báo khi lệch. File không từng được Excel lưu thì cache có thể trống.

### 7.2 Sheet `COM_BOM`

- `B1:G1` (merge): title `Compatibility Matrix - Hardware to Software`. Header ở hàng 2, dữ liệu từ hàng 3.
- Cột: B `ECU NAME` (merge dọc theo nhóm), C `PU PN`, D `HW PN`, E `SW PN` (merge dọc: một SW tương thích mọi HW trong vùng merge), F `BL Version` (merge dọc, có thể theo nhóm nhỏ hơn SW), G `Remark` (trống trong sample).
- Điền giá trị ô merge xuống các hàng con trước khi lập bảng.
- Cùng một HW có thể xuất hiện nhiều lần với **nhiều SW** (2IN1 (VN): `EEP69072001AC-01` đi với `...AA-04` và `...AA-05`): quan hệ HW-SW là nhiều-nhiều.
- Tên ECU có hậu tố market: `MHU VN`, `2IN1 (VN)`, `2IN1 (PHL)`; ECU không hậu tố: `SS`, `ACM`, `EAC`.
- `PU PN` lúc có rev (`EEP69072000AD-01`), lúc không (`EEP69021100AD`), có ký tự trắng đầu (`' EEP69081000AE'`): chuẩn hóa trước khi nối với cột L của BOM.
- Khoá so khớp tương thích: (ECU + market, HW PN đầy đủ rev, SW PN đầy đủ rev, BL Version).

### 7.3 Sheet `Change content ` (khoảng trắng cuối)

- `A1:D1` (merge): `FRS 3B.1.11.0`. Header ở hàng 2: A `TPV`, B `ECU`, C `Change content`, D `Remarks`; dữ liệu từ hàng 3.
- Cột A merge dọc theo TPV (TPV8 đến TPV1, mới nhất ở trên). Điền xuống các hàng con. Có TPV chỉ một hàng, không merge (TPV3).
- Cột B tên ECU có biến thể so với BOM: `BMS (CKD VN)`, `BMS (CKD)`, `BMS (Low-cost VN)`, `BMS (Low-cost PHL)`, `BMS (Low-cost)`, `BCM ` (khoảng trắng cuối), `2IN1` và `2in1`. Cần ánh xạ sang ECU + block của BOM (qua nhãn ở cột R và market), phần không chắc chắn đưa vào màn hình duyệt alias.
- Cột C là text tự do, nhiều dòng, trộn ba loại: (1) mô tả thay đổi không có ticket (vd EAC TPV8), (2) ticket CCB/VF3/VF5/GTSC/MINIOGREEN kèm tiêu đề, (3) ghi chú `Carry over from FRS ...`, `Carry across SW from FRS ...`, `Lesson learnt: ...`. Dòng ticket có dạng `KEY<tab>tiêu đề`, `[KEY] tiêu đề - VinFast TMS`, hoặc `GTSC-7888] ...` (ngoặc lệch).
- Cột D ghi chú phạm vi áp dụng: `Apply to VN Facelift`, `Apply to VN BCO2 & Phil BCO`, `Apply to Phil BCO`, `No new SW update, only new CCB is added ...`. Lưu nguyên văn và gắn vào ECU của hàng đó.
- Sample có khoảng 160 key ticket (CCB: 39, VF3: 116, VF5: 1, GTSC: 1, MINIOGREEN: 1). Không có key `IMS` nào trong sample.
- Có hàng ECU nhưng nội dung trống (`BMS (Low-cost PHL)` ở TPV5, `2in1` ở TPV1): giữ lại, đánh dấu "không có nội dung".

### 7.4 Đối chiếu BOM với COM_BOM (kết quả chạy thử trên sample)

Nối theo (ECU, market, HW, SW, BL) cho 15 block: 5 block khớp (ACM, MHU block VN FL/VN BCO2, EAC, 2IN1 VN, 2IN1 PHL), 2 block **thiếu** trong COM_BOM (MHU block PHL BCO, SS), 8 block thuộc ECU không có trong COM_BOM nên không kiểm tra (BCM, CVCLW, EDS, EPS, ABS, 3 block BMS). Hai trường hợp thiếu là dữ liệu thật để kiểm thử FR-31 (AC-03).

## 8. Tiêu chí chấp nhận (v1)

- AC-01: Parse `docs/sample.xlsx` ra đúng 15 block của 11 ECU (ACM 1, BCM 1, MHU 2, CVCLW 1, EDS 1, EAC 1, EPS 1, ABS 1, BMS 3, 2IN1 2, SS 1) và 49 part row; DID/VF PN/Rev/PU PN tính lại khớp giá trị cache của file.
- AC-02: Tìm một PN bất kỳ trong file mẫu trả đúng ECU, FRS, variant xe, kể cả khi PN có khoảng trắng thừa.
- AC-03: Truy vấn COM_BOM đúng cho SW có ô merge dọc; cảnh báo đúng 2 block thiếu (MHU PHL BCO, SS) và không cảnh báo 8 block thuộc ECU không có trong COM_BOM; trả "không tương thích" khi HW đi với SW số khác.
- AC-04: Change content của sample đủ TPV1..TPV8 (TPV3 một hàng không merge vẫn đúng), ticket CCB/VF3/VF5/GTSC/MINIOGREEN thành link và không khớp nhầm PN như `SOW69011004AD-05`; tìm `CCB-26107` ra đúng các TPV/ECU, và FRS ra đủ CCB/IMS.
- AC-05: Cây FRS dựng đúng ví dụ `3B.1.7.0 -> 3B.1.8.0 -> 3B.1.9.0 -> 3B.1.9.1 -> 3B.1.9.2` và nhánh phụ `3B.1.8.0 -> 3B.1.8.1 -> 3B.1.8.2`.
- AC-06: Thư mục có `V6`, `V7`, `V8` của cùng FRS thì chỉ V8 được dùng.
- AC-07: So sánh hai FRS cho ra bảng khác biệt part number đúng.

## 9. Rủi ro

- Dữ liệu bẩn (PN gãy, thiếu Rev, `#VALUE!`).
- Quy tắc cha-con theo mã FRS có ngoại lệ (nhảy số, FRS đặc biệt): đã có sửa tay (FR-36).
- Tên ECU không đồng nhất giữa các sheet: cần bước duyệt alias.
- Ý nghĩa segment ngoài `1` và `6` (vd `8` trong `3B.8.7.0`) chưa rõ.
- Số file tăng nhiều trong tương lai (NFR-09).

## 10. Câu hỏi còn lại

Đã được trả lời nhờ `sample.xlsx` (không cần hỏi nữa): cấu trúc cột/hàng (mục 7), template duy nhất, market suy từ nhãn variant, cột công thức F/G/I/L.

1. (Câu 7 cũ) Sample cho một ví dụ thật: BMS có 3 block, hai block (VN BCO2 và PHL BCO) cùng HW PN `BAT69011016AA-01` nhưng khác Purchase PN và khác SW. Khi tìm PN `BAT69011016AA-01`, hiển thị một dòng gộp "BMS, VN BCO2 + PHL BCO" rồi mở rộng ra từng block, hay luôn tách hai dòng? Mặc định: gộp theo (ECU, PN), mở rộng ra block.
2. IMS: định dạng key (`IMS-12345`?) và có link web riêng không? Sample không có key IMS nào. `MHU3-12705813` (trong CCB-26107) có phải là một key cần tra cứu không?
3. Cột M (Purchase PN after Reflashing) và N (Purchase Remarks) trống trong sample: có dự án nào dùng, và khi có thì cột nào (K hay M) là PU PN "hiện hành" để so sánh và nối COM_BOM?
4. Nhãn block ở cột R (`VN FL: BMS (CKD)`, `VN with PTC`, `Phil non PTC`) là text tự do. Chấp nhận để tool giữ nguyên văn và ghép gần đúng với tên ECU trong Change content (`BMS (CKD VN)`...) rồi cho bạn duyệt?
5. Một FRS có thể thuộc nhiều line (D4): file Excel có ghi line nào không, hay bạn gán tay trong tool?
6. Segment ngoài `1` và `6` (vd `8` trong `3B.8.7.0` xuất hiện trong tiêu đề ticket): hiển thị số thô, hay đặt nhãn trong màn hình cấu hình?
7. FRS có minor = 0 mà major - 1 không tồn tại (vd `3B.1.7.0`): coi là gốc cây, đúng không?
8. File có tên lạ (`V8_final`...): chọn theo số V lớn nhất hay thời gian sửa mới nhất? (Tên file sample là `sample.xlsx` nên tên thật chưa thấy.)
9. Quy ước đặt folder để suy ra line (vd `VF3\FL\`, `VF3\Legacy\LHD\`)?
