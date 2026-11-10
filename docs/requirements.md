# REQUIREMENTS: BOM Management Web Tool

Phiên bản: 0.2 (draft, đã cập nhật theo trả lời của người dùng)
Trạng thái: còn 6 câu hỏi nhỏ ở mục 10, không chặn việc bắt đầu Giai đoạn 1.

Lưu ý nguồn dữ liệu: tài liệu được viết từ brief và các quan sát đã xác nhận từ dump Excel (VF3 FL FRS 3B.1.11.0 V8, VF3 Legacy FRS 3A.1.11.0 V6, EBUS BG.1.9.4). Các file sample gốc nằm trên máy người dùng nên chưa được đối chiếu trực tiếp. Mọi chi tiết cột/hàng cần xác nhận lại khi viết parser.

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
| D6 | Template EBUS chỉ khác VF3 ở: không có cột "before Reflashing" và có cột `VSR COMMENTS`. Không có template mới sắp tới (kể cả ECVan). Parser vẫn detect cột theo text header. |
| D7 | COM_BOM chỉ có hai trạng thái: tương thích hoặc không. Tương thích khi bộ ba (ECU, HW PN, SW PN) có trong bảng. Không có trong bảng, hoặc có HW đó nhưng đi với SW số khác, là không tương thích. |
| D8 | Cặp HW+SW không có trong COM_BOM: chỉ **cảnh báo**, không chặn. |
| D9 | BOM, PN và mọi thông tin kèm theo chỉ đọc từ Excel. **FRS được phép tạo thêm trong tool** (gắn với line, gắn với file Excel) và truy xuất từ file Excel. |
| D10 | So sánh hai FRS tập trung vào **ECU part number** (HW, SW, BL, SW_BASIC, SW_APP, CAL...). |
| D11 | Alias tên ECU lấy từ chính file Excel (tên chuẩn ở cột A, tên theo system ở cột D, tên ở COM_BOM/Change content). Tool tự ghép, cho người dùng duyệt các ghép nối không chắc chắn. |
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
- FR-09: Hỗ trợ template VF3 và template EBUS (D6). Parser phải chịu được thay đổi nhỏ về cột.
- FR-10: Parser dừng khi gặp N hàng trống liên tiếp (sheet có thể có hơn 1 triệu hàng định dạng). Tham chiếu `EMPTY_STREAK_STOP=50` của `frs_parser.py`.
- FR-11: Quét lại (rescan) theo thời gian sửa file/hash: chỉ parse lại file đổi. Khi xuất hiện V mới hơn của cùng FRS thì thay thế TPV cuối và hiển thị diff so với bản trước.
- FR-12: Line suy ra từ folder và tên file (D12); mâu thuẫn thì hiển thị để chọn.

### 5.3 ECU và part
- FR-13: Mỗi ECU hiển thị các dòng PN Type: HW, SW, BootLoader, SW_BASIC, SW_APP, CAL, FL DRV, XML, FONT, HMI, TBOX..., kèm DID, VF PN, Rev, Purchase Level, Purchase PN, Remarks.
- FR-14: Một ECU có thể có nhiều block (variant ECU theo market/supplier: MHU, BMS, 2IN1, ABS, BCM...). Tool giữ các block riêng, gom dưới cùng một ECU, mỗi block kèm danh sách variant xe áp dụng (X) và không áp dụng (O).
- FR-15: Chuẩn hóa tên ECU (alias) theo D11; hiển thị cả tên gốc.
- FR-16: Cột merge theo block (Purchase PN, Remarks) được đọc đúng: giá trị gắn cho cả block.

### 5.4 Change content và ticket
- FR-17: Đọc sheet `Change content ` (có trailing space), detect hàng header (có file ở row 1, có file ở row 2 sau title).
- FR-18: Lưu theo (TPV, ECU, nội dung, remarks); TPV merge dọc gom nhiều ECU.
- FR-19: Trích ticket bằng regex: `CCB-\d+`, `IMS-\d+` (cần xác nhận định dạng IMS, mục 10), `VF3-\d+`, `VF3RHD-\d+`, `MINIOGREEN-\d+`, `GTSC-\d+`. Hiển thị link `https://tms.vinfast.vn/browse/<KEY>` cho key Jira.
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
- FR-31: Cảnh báo (không chặn) khi BOM của một FRS có cặp HW+SW không nằm trong COM_BOM (D8).
- FR-32: Câu hỏi thường dùng: "SW mới nhất của ECU X có tương thích HW cũ không?" có nút trả lời nhanh.
- FR-33: Ánh xạ PU PN với HW PN và tên ECU có hậu tố variant (`MHU VN`, `BCM PHL`, `BMS (FBU)`, `2IN1 (PHL)`).

### 5.7 Sơ đồ cây FRS
- FR-34: Dashboard hiển thị cây FRS theo line, mở rộng/thu gọn, zoom, click nút để mở chi tiết.
- FR-35: Quan hệ cha-con **suy ra tự động từ mã FRS** (trong cùng family và segment):
  - Minor > 0: cha là cùng major, minor - 1 (`3B.1.8.1` cha là `3B.1.8.0`; `3B.1.9.2` cha là `3B.1.9.1`).
  - Minor = 0: cha là major - 1, minor 0 (`3B.1.9.0` cha là `3B.1.8.0`).
  - Hệ quả: `3B.1.8.0` có hai con, `3B.1.9.0` (nhánh chính) và `3B.1.8.1` (nhánh phụ), đúng với ví dụ người dùng.
  - Khi FRS cha không có trong dữ liệu (chưa có file): nút cha hiển thị dạng "thiếu", hoặc nối lên tổ tiên gần nhất có sẵn.
- FR-36: Người dùng sửa tay cha-con (gán lại cha, tách nhánh) khi quy tắc suy ra sai. Quan hệ sửa tay luôn thắng quy tắc tự động.
- FR-37: Sheet `FRS x.x.x.x BOM (for FOTA)` và ghi chú carry-across dùng làm **gợi ý** để đối chiếu với cây suy ra, cảnh báo khi mâu thuẫn.
- FR-38: Cây dùng được cho nhiều segment (LHD `3B.1.x` và RHD `3B.6.x` là hai cây/nhánh riêng, có thể bật/tắt).

### 5.8 Sheet Data
- FR-39: Đọc sheet `Data` làm danh mục tham chiếu: PN Type, Carry Over Information, CAN DBC version, SW Update Compatibility (FOTA Only, FOTA+OBD, FOTA+USB, FOTA+Bench (VF), OBD Only, Bench Only (VF), Supplier Only).

### 5.9 Chất lượng dữ liệu
- FR-40: Chuẩn hóa khi đọc (strip, gộp khoảng trắng) nhưng GIỮ giá trị gốc để đối chiếu.
- FR-41: Báo cáo data quality cho mỗi lần quét: PN gãy (`SOW690740 03AA-01`), PN cụt (`EEP69081000A`), `#VALUE!`, thiếu Rev, khác biệt giữa BOM và COM_BOM. Trang xem được trong tool.
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

## 7. Quy tắc parser (tóm tắt)

- Chọn sheet BOM chính bằng header chứa `COMMON ECU NAME` (tham chiếu `select_bom_sheet`).
- Header ở row 3, dữ liệu từ row 4 (`DATA_START_ROW=4`), nhưng phải detect, không tin vị trí cố định.
- Cột: A Common ECU Name, B PN Type, C VF PN with Revision, D Component name as per system, E PN Type, F DID No, G VF PN, H Rev DID, I Rev, J Purchase Level, K Purchase Part Number with Rev, L before Reflashing, M after Reflashing, N Purchase Remarks, O.. cột variant xe (X/O), cuối là Remarks / Change Content.
- DID: HW = F191/F141, SW = F188/F148, BootLoader = F101 (không có rev, hex 4 ký tự), SW_BASIC = F105/F145, SW_APP = F104/F144, CAL = F102/F142. Purchase Level = `D`.
- Purchase PN gắn với HW của block.
- Row 2 có thể chứa tên market (`VN`, `PHL`, `LAOS`) trên các cột variant; row 3 chứa tên variant (`VN FL`, `VN BCO2`, `Base`).

## 8. Tiêu chí chấp nhận (v1)

- AC-01: Quét đúng 3 file mẫu, số ECU/block/part khớp đếm tay ở ít nhất 3 ECU mỗi file.
- AC-02: Tìm một PN bất kỳ trong file mẫu trả đúng ECU, FRS, variant xe, kể cả khi PN có khoảng trắng thừa.
- AC-03: Truy vấn COM_BOM đúng cho SW có ô merge dọc, và trả "không tương thích" khi HW đi với SW số khác.
- AC-04: Change content của FRS 3B.1.11.0 đủ TPV1..TPV8, ticket thành link; tìm một CCB ra đúng FRS/ECU, và FRS ra đủ CCB/IMS.
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

Q7 trước đó chưa rõ nên diễn đạt lại bằng ví dụ:

7. Trong cùng một FRS, ECU BMS có hai block, ví dụ block "CKD" và block "Low cost VN". Giả sử cả hai cùng ghi HW PN `ABC-01`, nhưng block CKD áp dụng cho variant `VN FL`, còn block Low cost VN áp dụng cho `VN BCO2`. Khi tìm PN `ABC-01`, bạn muốn kết quả hiện **một dòng** "BMS, dùng cho VN FL và VN BCO2", hay **hai dòng** tách theo block? Mặc định đề xuất: gom theo ECU + PN, liệt kê các block và variant bên dưới.

Các câu nhỏ còn lại:

8. IMS có định dạng key thế nào (`IMS-12345`, hay khác)? Có link web riêng không?
9. Với nhiều line dùng chung một FRS (D4): chỉ cần gán thủ công trong tool, hay file Excel có chỗ nào ghi sẵn line nào dùng FRS đó?
10. Các segment khác ngoài `1` và `6` (như `8` trong `3B.8.7.0`) bạn muốn tool xử lý ra sao: hiển thị số thô, hay bạn muốn đặt nhãn cho từng số trong màn hình cấu hình?
11. Với FRS có minor = 0 mà major - 1 không tồn tại (vd bắt đầu từ `3B.1.7.0`, không có `3B.1.6.0`): coi là gốc cây, đúng không?
12. Nếu cùng một FRS có V cao nhất nhưng tên file khác định dạng (vd `V8_final`, `V8_rev2`), tool cần quy tắc chọn nào: lấy số V lớn nhất, hay theo thời gian sửa file mới nhất?
13. Tên folder trong thư mục dự án có quy ước nào để suy ra line (vd `VF3\FL\`, `VF3\Legacy\LHD\`) không, hay bạn sẽ đặt tên theo quy ước mới khi triển khai?
