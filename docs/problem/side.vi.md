# Wave-2 ngân hàng side-project và nghiên cứu

**Ngày bổ sung ý tưởng:** 23 tháng 9 năm 2026. 35 đề xuất này bổ sung cho ngân hàng side-project đầu tiên; chúng là các thí nghiệm ứng viên, không phải khoảng trống triển khai đã xác nhận hay lợi ích đã đo lường. Chúng tách biệt với loạt tháng Bảy (user-guide RAG, Sales/Aftersales Playwright, chuẩn hóa EN/VN), các dự án 1–10, và UT/TC/AR/AU/OP. Ưu tiên dữ liệu xuất đã được làm sạch, metadata đã lưu và fixture cục bộ hơn là ghi trực tiếp vào production.

Mỗi MVP giả định một thực tập sinh, một module hoặc quy trình làm việc, có mentor sẵn sàng và dữ liệu mẫu có thể truy cập được. **S** nghĩa là ước tính 1–2 tuần tập trung; **M** nghĩa là 3–4 tuần tập trung, chưa tính thời gian chờ cấp quyền và sắp xếp lịch song song với dự án. Đây là ước lượng kế hoạch, không phải cam kết giao hàng.

---

## 1. Chất lượng dữ liệu: phát hiện mâu thuẫn trong master và export giao dịch

Làm việc trên các bản trích xuất CSV/JSONL đã làm sạch và metadata đã lưu. Không coi các pilot này như một data warehouse hoặc như thẩm quyền sửa bản ghi trực tiếp.

### DQ1. Bộ tìm cặp tài khoản trùng lặp (M)

- **Tech stack đề xuất:** Python, pandas, một khóa chặn (ví dụ số điện thoại hoặc mã số thuế đã chuẩn hóa) cộng với rapidfuzz hoặc scikit-learn để đo độ tương đồng chuỗi; Streamlit cho hàng đợi mentor duyệt; SQLite lưu quyết định gắn nhãn; pytest với fixture có cặp trùng lặp cố ý.
- **MVP:** Xếp hạng các cặp tài khoản ứng viên từ một bản export đã làm sạch với các trường bằng chứng và hàng đợi chấp nhận/từ chối để mentor duyệt. Xuất CSV quyết định kèm phiên bản quy tắc chấm điểm.
- **Nghiên cứu:** Kết hợp chặn với đo độ tương đồng có tìm được nhiều cặp trùng thật hơn so với khớp khóa chính xác ở cùng ngưỡng false-positive không?
- **Đánh giá:** Precision và recall trên mẫu mentor gắn nhãn; thời gian duyệt mỗi quyết định. Không bao giờ tự động gộp; giữ đề xuất gộp ở vai trò tham khảo.

### DQ2. Bộ kiểm tra nhất quán VIN và master xe (S)

- **Tech stack đề xuất:** Python, pandas và mô hình Pydantic cho các trường VIN, model, màu sắc và trạng thái; pytest fixture với mâu thuẫn cố ý; báo cáo Markdown bằng Jinja2.
- **MVP:** So sánh một bản export thông tin xe với master sản phẩm/model liên kết và liệt kê các thuộc tính mâu thuẫn cùng định danh bản ghi.
- **Nghiên cứu:** Nhóm quy tắc nào (thiếu, mâu thuẫn, tổ hợp bất khả thi) chiếm ưu thế trên một bản trích xuất thực?
- **Đánh giá:** Precision của quy tắc theo phán quyết của mentor và cảnh báo sai trên các dòng đã biết là tốt. Coi quy tắc checksum VIN là tùy chọn và theo vùng miền.

### DQ3. So sánh option-set giữa các môi trường (M)

- **Tech stack đề xuất:** Python, hai bản export metadata Dataverse đã lưu (JSON hoặc XML), mô hình option-set bằng Pydantic, deepdiff hoặc diff cấu trúc viết tay, Jinja2 HTML/Markdown. Lệnh gọi PAC hoặc Web API nằm ngoài MVP nếu đã có sẵn export.
- **MVP:** So sánh nhãn, giá trị và mã trạng thái của các option-set được một thực thể thống nhất sử dụng giữa DEV và UAT65 (hoặc UAT65 và PROD) chỉ dựa trên bản export đã lưu.
- **Nghiên cứu:** Tần suất drift chỉ ở nhãn (không kèm drift giá trị) và liệu điều đó có làm BA nhầm lẫn khi so sánh không?
- **Đánh giá:** Độ chính xác khớp trên một cặp export có gieo hạt và các diff hành động được mentor xác nhận. Báo cáo tách riêng giá trị bị xóa với nhãn bị đổi tên.

### DQ4. Bộ lấy mẫu lookup hỏng (S)

- **Tech stack đề xuất:** Python/pandas trên một cặp CSV cha/con đã làm sạch; SQLite để cache mồ côi; tóm tắt bằng Jinja2. Ưu tiên join offline trước khi thăm dò Web API trực tiếp.
- **MVP:** Với một quan hệ cha/con, lấy mẫu các dòng con mà lookup trỏ đến cha bị thiếu hoặc không hoạt động và tạo ra số đếm cùng các ID tiêu biểu.
- **Nghiên cứu:** Tham chiếu đến cha không hoạt động có khác biệt đáng kể so với mồ côi cứng trong quy trình đã chọn không?
- **Đánh giá:** Đối chiếu đúng/sai của phép join và tính ổn định của số đếm qua hai ngày trích xuất. Giới hạn kích thước mẫu; tránh truy xuất trực tiếp hàng loạt trong MVP.

### DQ5. Bộ phát hiện lệch ngày theo UserLocal (S)

- **Tech stack đề xuất:** Python, `zoneinfo`, pandas và pytest fixture được dựng từ case lịch sử bảo hành đã được tài liệu hóa trong [warranty-history-userlocal-date-mismatch-2026-09-22.md](../power-apps/warranty-history-userlocal-date-mismatch-2026-09-22.md); Jinja2 cho báo cáo điều tra ngắn.
- **MVP:** Với cặp giá trị UTC thô và DateOnly/UserLocal trên UI cho một họ thuộc tính, đánh dấu các trường hợp lệch ranh giới ngày và giải thích phép tính múi giờ kèm trường bằng chứng.
- **Nghiên cứu:** Một bộ kiểm tra tất định có tái tạo được lệch PROD đã biết và tìm ra các cặp tương tự trong bản export đã làm sạch không?
- **Đánh giá:** Phát hiện fixture được gieo, bằng không cảnh báo sai trên các ca cùng ngày, và liên kết bằng chứng rõ ràng. Giữ khuyến nghị xử lý ở vai trò tham khảo; không viết lại bảng lịch sử trong pilot.

---

## 2. Độ tin cậy tích hợp: kiểm tra payload đã lưu và bằng chứng job

Tách biệt với dự án 3 (triage App Insights trực tiếp), AU2 (phân loại log CI) và TC5 (bộ unit test fault-injection). Bắt đầu từ artifact offline.

### IR1. Snapshot hợp đồng payload đi (M)

- **Tech stack đề xuất:** CLI Python, Pydantic hoặc JSON Schema cho một thông điệp đi kiểu `Send*`, JSONL request/response vàng, test hợp đồng pytest, báo cáo drift bằng Jinja2. Ưu tiên payload đã chụp đã làm sạch hơn là gọi trực tiếp SAP hoặc MuleSoft.
- **MVP:** Đóng băng schema cho một thông điệp tích hợp đi và kiểm tra một thư mục payload đã lưu, báo cáo trường thiếu, lệch kiểu và thuộc tính ngoài dự kiến.
- **Nghiên cứu:** Một snapshot schema có bắt được nhiều thay đổi trường phá vỡ hơn so với checklist trường không chính thức trên cùng tập dữ liệu không?
- **Đánh giá:** Precision trên các phá vỡ schema được gieo và cảnh báo sai trên các trường tùy chọn hợp lệ. Đánh version schema cùng fixture.

### IR2. Bản tóm tắt lỗi interface log (S)

- **Tech stack đề xuất:** Python/pandas trên một bản export log interface hoặc Service Bus đã làm sạch; regex cộng clustering TF-IDF; digest bằng Jinja2; LLM client chỉ dùng tùy chọn để đặt tên cụm sau khi đã tính count.
- **MVP:** Tóm tắt các dòng interface lỗi trong một ngày theo chữ ký, khối lượng, lần đầu/cuối thấy và ứng viên runbook liên kết.
- **Nghiên cứu:** Digest đã gom cụm có rút ngắn thời gian triage của mentor so với CSV lỗi thô không?
- **Đánh giá:** Độ tinh khiết cụm trên mẫu gắn nhãn, tỷ lệ khẳng định không có bằng chứng nếu dùng tên cụm từ LLM, và thời gian sinh digest. Chỉ offline trong MVP.

### IR3. Phát lại callback idempotent (M)

- **Tech stack đề xuất:** Fake cục bộ bằng C# hoặc Python khớp hợp đồng callback đã chọn; script giao hàng trùng lặp tất định; sổ cái side-effect bằng SQLite; assertion pytest hoặc xUnit trên số đếm create/update. Tái sử dụng doubles của DMS_LOCAL_HOST khi handler đã chạy ở đó.
- **MVP:** Phát lại một callback đến với các bản giao hàng trùng lặp và lệch thứ tự trên một fake cục bộ và chứng minh số side-effect theo đúng ý định.
- **Nghiên cứu:** Khóa trùng lặp nào (message id, business key, correlation id) thực sự bảo vệ handler khi test?
- **Đánh giá:** Số side-effect đúng, phát hiện được double-write và thiếu đường phục hồi. Giữ đảm bảo broker thật là bộ test sau, dán nhãn riêng.

### IR4. Baseline thời lượng job Hangfire (S)

- **Tech stack đề xuất:** Python/pandas trên CSV lịch sử Hangfire hoặc job đã export; phân vị với Plotly; baseline tuần bằng Jinja2. Ưu tiên export chỉ-đọc từ bảng job của host DMS API hoặc dashboard đã lưu.
- **MVP:** Với một job định kỳ, vẽ biểu đồ phân vị thời lượng qua một cửa sổ cố định và đánh dấu các lần chạy vượt ngưỡng thống nhất, kèm ghi chú revision và kích thước dữ liệu khi có.
- **Nghiên cứu:** Một baseline phân vị đơn giản có phát hiện hồi quy sớm hơn giám sát chỉ dựa trên mean trên cùng chuỗi không?
- **Đánh giá:** Đồng thuận với chạy chậm được mentor gắn nhãn và tỷ lệ cảnh báo sai. Tài liệu hóa cold start và sự cố phụ thuộc như các danh mục riêng.

### IR5. Bộ phát hiện retry-storm (S)

- **Tech stack đề xuất:** Python/pandas chuỗi thời gian trên các counter retry hoặc dead-letter đã làm sạch; quy tắc cửa sổ trượt trước tiên; Streamlit tùy chọn để kiểm tra.
- **MVP:** Phát hiện các đợt bùng nổ khi cùng một interface retry vượt ngưỡng trong một cửa sổ ngắn và phát cảnh báo Markdown kèm các chữ ký hàng đầu.
- **Nghiên cứu:** Cửa sổ cố định tách storm khỏi backfill qua đêm dự kiến tốt đến đâu?
- **Đánh giá:** Precision/recall trên các storm được gieo trong chuỗi lịch sử; bỏ qua khi khối lượng quá nhỏ để phán xét. Ghép với IR2 thay vì thay thế triage App Insights.

---

## 3. Quyền riêng tư và rà soát quyền truy cập: chỉ kiểm tra phòng thủ

Các pilot này rà soát dữ liệu và cấu hình. Chúng không cấp quyền cao hơn, trích xuất bí mật hay công bố quy trình tấn công.

### PA1. Bộ lint PII tập dữ liệu (S)

- **Tech stack đề xuất:** CLI Python, regex và heuristic theo tên cột, tùy chọn `presidio-analyzer` nếu được duyệt cho workstation; pytest fixture với PII gieo sẵn; exit code cho pre-commit hoặc CI. Chỉ quét các đường dẫn thực tập sinh sở hữu (golden JSONL, CSV mẫu).
- **MVP:** Đánh dấu khả năng chứa tên, số điện thoại, email, CMND/CCCD và blob văn bản tự do trong một golden dataset dự kiến trước khi commit, kèm file suppressions cho các trường tổng hợp đã biết.
- **Nghiên cứu:** Heuristic cột cộng regex có thắng regex-đơn-lẻ trên các cột được mentor gắn nhãn không?
- **Đánh giá:** Precision/recall trên PII gieo sẵn, cảnh báo sai trên ID tổng hợp và thời gian dọn một file đang lỗi. Không bao giờ in nguyên giá trị bí mật trong báo cáo.

### PA2. Bộ kiểm tra allowlist trường log (S)

- **Tech stack đề xuất:** C# Roslyn hoặc scan regex trên một dự án plugin/API; allowlist JSON cho các template log được phép; pytest/xUnit cho fixture quy tắc; báo cáo Markdown. Liên kết với script gitleaks và secret-scan plugin hiện có như các cổng bổ sung.
- **MVP:** Đánh dấu các câu `ILogger`/`Trace` nội suy thuộc tính thực thể nằm ngoài allowlist (ví dụ mật khẩu, token, toàn bộ body request).
- **Nghiên cứu:** Allowlist có giảm nhiễu so với quy tắc "không entity ToString" tràn lan không?
- **Đánh giá:** Precision trên các pattern rò rỉ lịch sử và bỏ sót trên mẫu gắn nhãn. Bắt đầu với một assembly.

### PA3. Bộ giải thích quyền security-role (M)

- **Tech stack đề xuất:** Python XML parser cho một security role đã export, mô hình privilege bằng Pydantic, tường thuật Jinja2; LLM client tùy chọn chỉ được phép diễn giải lại các trường đã có trong XML. pytest kiểm tra mọi khẳng định đều trích dẫn một nút privilege.
- **MVP:** Tạo bản tóm tắt quyền dạng người-đọc-được cho một role (create/read/write/delete và phạm vi append theo bảng) kèm trích dẫn về bản export.
- **Nghiên cứu:** Diễn giải bằng LLM có giúp BA nhanh hơn bảng có cấu trúc khi hallucination bị chặn bởi kiểm tra trích dẫn không?
- **Đánh giá:** Độ chính xác claim-sang-XML và điểm hữu dụng BA. Loại bỏ mọi câu không trỏ được về một hàng privilege.

### PA4. Bộ lấy mẫu audit spike (M)

- **Tech stack đề xuất:** Tái sử dụng pattern của skill export-dataverse-audit-history; Python/pandas trên một bản export audit đã lưu; Plotly cho khối lượng theo user và thực thể; tóm tắt Jinja2. Chỉ-đọc; không thay đổi cấu hình audit.
- **MVP:** Tóm tắt khối lượng audit bất thường cho một thực thể qua một cửa sổ cố định với top user, thao tác và ID bản ghi mẫu.
- **Nghiên cứu:** Baseline đơn giản nào (median theo ngày trong tuần, rolling z-score) khớp nhãn "bất thường" của mentor nhất?
- **Đánh giá:** Precision trên các spike được gieo và chất lượng giải thích. Giữ đầu ra trong phạm vi mentor duyệt; coi là bằng chứng điều tra.

### PA5. Bộ fixture prompt-injection cho RAG (S)

- **Tech stack đề xuất:** Fixture JSONL có version, scorer của dự án 4, LLM client dùng chung và retrieval stub của assistant mục tiêu. Chấm điểm xem câu trả lời có trung thực với tài liệu truy xuất và từ chối chỉ dẫn ngoài phạm vi không. Chỉ đánh giá phòng thủ; không công bố quy trình khai thác hay payload nhắm production.
- **MVP:** Một bộ fixture gồm prompt người dùng lành tính và đối kháng cho một RAG assistant, với rubric pass/fail cho độ trung thực trích dẫn và thứ bậc chỉ dẫn.
- **Nghiên cứu:** Nhóm fixture nào thường xuyên nhất gây mất trích dẫn hoặc vượt policy trên assistant đã chọn?
- **Đánh giá:** Đồng thuận scorer với nhãn mentor và phát hiện hồi quy khi prompt thay đổi. Giữ fixture nội bộ trong repo đánh giá.

---

## 4. Bản địa hóa và thuật ngữ: kiểm kê khoảng trống mà không sở hữu công cụ viết lại

Dự án chuẩn hóa EN/VN tháng Bảy vẫn là chủ sở hữu việc viết lại. Các ý tưởng này chỉ kiểm kê, so sánh và test.

### LG1. Kiểm kê nhãn chưa dịch (S)

- **Tech stack đề xuất:** Python trên JSON localized-label đã export từ Dataverse hoặc XML solution; pandas; báo cáo Jinja2. Giới hạn một thực thể hoặc một solution.
- **MVP:** Liệt kê các thuộc tính, view và nhãn option-set thiếu giá trị localized tiếng Việt hoặc tiếng Anh so với ngôn ngữ gốc.
- **Nghiên cứu:** Bao nhiêu lần "thiếu" thực ra là tái sử dụng cố ý chuỗi gốc?
- **Đánh giá:** Precision sau khi mentor duyệt một mẫu và tính ổn định qua hai bản export. Xuất CSV kiểm kê, không xuất chuỗi đã viết lại.

### LG2. Bộ kiểm tra drift glossary (S)

- **Tech stack đề xuất:** Python, `markdown-it-py` để parse [glossary.md](../glossary.md), trích term từ một cây con tài liệu, pytest cho glossary fixture, báo cáo drift Jinja2.
- **MVP:** Tìm các thuật ngữ dùng trong một thư mục tài liệu đã chọn mà không có mục glossary, và các mục glossary không được tham chiếu trong thư mục đó.
- **Nghiên cứu:** Stemming hoặc danh sách alias đơn giản có cải thiện kết quả hữu ích so với khớp chính xác không?
- **Đánh giá:** Ứng viên thuật ngữ mới mentor chấp nhận và cảnh báo sai trên định danh code. Đề xuất bản vá glossary; không tự động sửa glossary trong CI nếu chưa duyệt.

### LG3. Báo cáo parity chuỗi UI song ngữ (M)

- **Tech stack đề xuất:** Python/pandas so sánh các export resource hoặc nhãn EN và VN; kiểm tra tỷ lệ độ dài và token placeholder; LLM client tùy chọn cho điểm tương đồng ngữ nghĩa trên một mẫu; duyệt bằng Streamlit.
- **MVP:** Báo cáo các cặp có placeholder lệch, một phía trống, hoặc tỷ lệ độ dài trông cực đoan cho một khu vực model-driven app.
- **Nghiên cứu:** Quy tắc placeholder và độ dài có bắt được nhiều khiếm khuyết BA-nhìn-thấy hơn so với chỉ tương đồng ngữ nghĩa không?
- **Đánh giá:** Precision trên các khiếm khuyết được gieo và thời gian duyệt. Bàn giao phát hiện cho chủ sở hữu chuẩn hóa tháng Bảy khi cần viết lại.

### LG4. Unit test định dạng locale (S)

- **Tech stack đề xuất:** Unit test C# hoặc JavaScript quanh một pure date/number formatting helper; fixture culture cố định; test runner hiện có của module.
- **MVP:** Khóa chuỗi mong đợi cho ICT và một culture thứ hai cho currency, DateOnly và DateTime hiển thị trên một màn hình.
- **Nghiên cứu:** Lỗi nào đến từ culture so với từ hành vi thuộc tính UserLocal (ghép với DQ5)?
- **Đánh giá:** Bắt được lỗi khi ai đó đổi format provider và bằng không phụ thuộc culture bất ổn trên máy agent. Giữ test tất định với culture tường minh.

### LG5. Danh mục thông điệp lỗi hướng người dùng (M)

- **Tech stack đề xuất:** C# Roslyn hoặc regex trích từ một dự án plugin; catalog CSV/JSON; LLM client tùy chọn để soạn thảo văn bản rõ ràng hơn trong khi giữ mã lỗi; trang catalog Jinja2 theo phong cách DMS_DOCS.
- **MVP:** Kiểm kê các thông điệp hướng người dùng được throw với mã, vị trí nguồn và biến thể EN/VN có tồn tại hay không.
- **Nghiên cứu:** Bao nhiêu thông điệp là exception chỉ-dành-cho-dev đang lọt ra UI?
- **Đánh giá:** Tính đầy đủ của catalog trên một assembly được lấy mẫu và đánh giá BA cho các bản viết lại gợi ý. Các gợi ý vẫn là đề xuất cho chủ sở hữu plugin.

---

## 5. Dẫn đường tri thức: con trỏ và cụm không cần nền tảng RAG đầy đủ

Tách biệt với dự án 6 (trợ lý runbook đa repo) và dự án 7 (FetchXML/SQL có thể thực thi). Ưu tiên liên kết, chỉ mục và clustering offline.

### KN1. Bộ kiểm tra trích dẫn skill (S)

- **Tech stack đề xuất:** Trình thu thập Markdown/liên kết Node hoặc Python trên `DMS_DOCS/.cursor/skills/**/SKILL.md` và các đường dẫn tham chiếu; pytest cho fixture liên kết hỏng; báo cáo Markdown.
- **MVP:** Xác minh mọi đường dẫn tương đối và tham chiếu skill trong cây skill đều resolve được, và liệt kê các skill không có liên kết đến từ `AGENTS.md` hoặc skill ngang hàng.
- **Nghiên cứu:** Skill mồ côi có tương quan với chỉ dẫn cũ trên một mẫu mentor gắn nhãn không?
- **Đánh giá:** Số liên kết hỏng thật tìm được, false positive trên URL ngoài cố ý và thời gian chạy dưới một phút cho cả cây. Chỉ-đọc.

### KN2. Bộ giải thích quan hệ catalog bảng (M)

- **Tech stack đề xuất:** Python trên một trang thực thể từ `docs/power-apps/tables/uat65/`; template giải thích Jinja2; LLM client tùy chọn bị ràng buộc chỉ trích dẫn trường và quan hệ có trên trang đó; kiểm tra trích dẫn pytest.
- **MVP:** Tạo bản giải thích một trang cho BA về các trường và quan hệ chính của một thực thể với anchor quay lại catalog.
- **Nghiên cứu:** Sinh có ràng buộc có thắng template thuần để BA hiểu mà không bịa trường không?
- **Đánh giá:** Độ chính xác trích dẫn và hữu dụng BA. Fail lần chạy nếu bất kỳ trường nào được đặt tên vắng mặt khỏi trang nguồn.

### KN3. Gom cụm chủ đề sự cố (M)

- **Tech stack đề xuất:** Python, TF-IDF và clustering của scikit-learn trên `docs/solutions/incidents/` và một số ghi chú hiệu năng đã chọn; trình duyệt cụm Streamlit; nhãn JSONL.
- **MVP:** Gom cụm các writeup sự cố lịch sử thành chủ đề và ánh xạ mỗi cụm sang runbook hoặc skill hiện có khi có khớp từ khóa.
- **Nghiên cứu:** Các cụm có bề mặt chủ đề mà mentor review cũng sẽ nhóm theo cùng cách không?
- **Đánh giá:** Mentor đồng thuận về nhãn cụm và các liên kết chéo hữu ích. Chỉ Markdown offline; không ghi Jira trong MVP.

### KN4. Báo cáo độ tươi runbook (S)

- **Tech stack đề xuất:** Python trên lịch sử Git (`git log` porcelain) cho `docs/runbooks/` và các skill đã chọn; pandas; báo cáo lão hóa Jinja2.
- **MVP:** Liệt kê các runbook cũ hơn một ngưỡng thống nhất tính từ commit nội dung gần nhất, với owner suy ra từ CODEOWNERS hoặc frontmatter khi có.
- **Nghiên cứu:** Tuổi commit có dự đoán staleness do mentor đánh giá tốt hơn file mtime đơn lẻ không?
- **Đánh giá:** Precision của cờ "cần duyệt" trên một mẫu gắn nhãn. Chỉ báo cáo; không tự đóng trang.

### KN5. CLI gợi ý trùng Jira (M)

- **Tech stack đề xuất:** Python `httpx` tìm kiếm Jira chỉ-đọc trên project VD (Atlassian MCP hoặc REST), tương đồng TF-IDF hoặc embedding trên văn bản summary/description, đầu ra Markdown CLI. Tôn trọng giới hạn `maxResults` theo quy ước workspace.
- **MVP:** Với một bản nháp summary issue, liệt kê top issue VD mở hoặc đóng gần đây tương tự nhất với liên kết và điểm tương đồng.
- **Nghiên cứu:** Thêm văn bản description có cải thiện gợi ý trùng so với chỉ khớp summary không?
- **Đánh giá:** Đánh giá liên quan do mentor trên các bản nháp được giữ lại và tỷ lệ trùng sai. Chỉ-đọc; không bao giờ tạo hay chuyển trạng thái issue từ MVP.

---

## 6. Phân tích quy trình: biểu đồ tất định từ các export đã làm sạch

Tách biệt với dự án 2 (khai phá free-text claim) và AR2 (tường thuật KPI bằng LLM). Tính trước; bình luận tùy chọn sau.

### WA1. Snapshot tuổi work-order (S)

- **Tech stack đề xuất:** Python/pandas, histogram Plotly và Jinja2 cho một bản export work order đã làm sạch; pytest trên tổng bucket.
- **MVP:** Chia work order mở theo tuổi và trạng thái cho snapshot một đại lý hoặc vùng, với tổng có thể tái lập.
- **Nghiên cứu:** Ngưỡng tuổi nào khớp thói quen triage của BA tốt hơn bin đều?
- **Đánh giá:** Tổng tính lại so với bản export nguồn và hữu dụng BA. Không khẳng định nhân quả trong tường thuật MVP.

### WA2. Đồ thị chuyển trạng thái (M)

- **Tech stack đề xuất:** Python trên các chuyển trạng thái từ lịch sử trạng thái hoặc audit cho NVSO hoặc work order; NetworkX hoặc ma trận kề đơn giản; sankey Plotly; fixture JSON.
- **MVP:** Xây đồ thị chuyển trạng thái với số đếm và median time-in-status giữa các trạng thái cho một quy trình.
- **Nghiên cứu:** Các cạnh bất ngờ có bộc lộ vấn đề cấu hình hoặc nhập liệu mà mentor đã biết không?
- **Đánh giá:** Đúng đồ thị trên một mini-trace gắn nhãn và ổn định qua hai bản trích. Tài liệu hóa chuyển trạng thái bất khả thi tách khỏi chuyển hiếm.

### WA3. Pareto từ chối bảo hành (S)

- **Tech stack đề xuất:** Python/pandas trên lý do từ chối đã mã hóa (không phải free text); biểu đồ Pareto với Plotly; Jinja2.
- **MVP:** Xếp hạng lý do từ chối theo khối lượng và tỷ trọng cho một cửa sổ model-year và xuất các số đếm nền.
- **Nghiên cứu:** Pareto hàng tuần có đổi ưu tiên BA so với rollup hàng tháng không?
- **Đánh giá:** Độ trung thực số đếm và mentor xác nhận rằng lý do hàng đầu là mã hành động được. Để clustering free-text cho dự án 2.

### WA4. Baseline thời gian chờ phụ tùng (M)

- **Tech stack đề xuất:** Python/pandas join timestamp yêu cầu phụ tùng và nhận đã làm sạch; chờ Kaplan–Meier đơn giản kiểu sống-sót hoặc phân vị; Plotly; pytest trên khóa join.
- **MVP:** Ước lượng phân phối thời gian chờ từ yêu cầu đến khả dụng cho một đường đi phụ tùng.
- **Nghiên cứu:** Median nhạy với yêu cầu bị hủy hoặc mở lại đến đâu?
- **Đánh giá:** Độ chính xác join và đồng thuận với mẫu đối chiếu của BA. Gắn nhãn rõ các ca censored.

### WA5. Baseline no-show lịch hẹn (M)

- **Tech stack đề xuất:** Python/pandas, hồi quy logistic của scikit-learn so với baseline tỷ lệ naive; tập đặc trưng cố định từ export lịch hẹn đã làm sạch; Streamlit để xem hệ số.
- **MVP:** So sánh một mô hình đơn giản với tỷ lệ no-show lịch sử trên một tuần giữ-lại cho một bản trích của trung tâm dịch vụ.
- **Nghiên cứu:** Đặc trưng nào (lead time, channel, model) cải thiện lift so với baseline naive?
- **Đánh giá:** Điểm AUC hoặc Brier so với baseline naive và biểu đồ hiệu chỉnh. Chỉ phân tích tham khảo; không tự động phạt hay liên hệ khách hàng từ pilot này.

---

## 7. Vệ sinh client và solution: form, script và đăng ký

Tách biệt với dự án 9 (pipeline deploy) và AR3 (tường thuật bằng chứng release). Ưu tiên formXML đã lưu, một web resource hoặc hai export solution.

### HY1. Kiểm kê lệnh gọi Xrm.WebApi (S)

- **Tech stack đề xuất:** Script Node với regex/AST trên một thư mục webresource; CSV các call site `Xrm.WebApi` và SOAP còn lại; tóm tắt Markdown. Ghép với `node --check` trên các file chạm vào.
- **MVP:** Kiểm kê các lệnh gọi retrieve/update/execute trong một họ script form với tham chiếu file và dòng.
- **Nghiên cứu:** Còn bao nhiêu SOAP bên cạnh Web API async trong khu vực đã chọn?
- **Đánh giá:** Tính đầy đủ so với đếm tay của mentor trên một file và bằng không crash parse trên file minify kèm theo khi cả hai tồn tại. Chỉ báo cáo; bản vá di trú nằm ngoài MVP.

### HY2. Bản đồ thứ tự script form onload (S)

- **Tech stack đề xuất:** Python XML parser cho một form đã export; danh sách có thứ tự của library và event handler; sơ đồ Jinja2 (Mermaid hoặc HTML).
- **MVP:** Tài liệu hóa thứ tự handler onload và onchange cho một form lưu lượng cao với tên và hàm webresource.
- **Nghiên cứu:** Làm thứ tự hiển thị có rút ngắn debug bug onload bị race không?
- **Đánh giá:** Khớp với form XML và mentor xác nhận. So sánh hai phiên bản form như phần mở rộng.

### HY3. Báo cáo command bar không dùng (M)

- **Tech stack đề xuất:** Python so sánh ribbon/command XML với enable rule và webresource handler; gợi ý sử dụng tùy chọn từ một export App Insights page-view đã làm sạch; Jinja2.
- **MVP:** Liệt kê các command trên một thực thể thiếu handler, luôn-hide rule, hoặc không có lượt gọi quan sát được trong export sử dụng được cung cấp.
- **Nghiên cứu:** "Không dùng" bao nhiêu lần là hành động đặc quyền hiếm so với UI chết thật?
- **Đánh giá:** Precision sau khi mentor duyệt; giữ thấp gợi ý "xóa tôi" sai. Không sửa ribbon trong MVP.

### HY4. Tóm tắt component solution-layer (M)

- **Tech stack đề xuất:** Python trên hai export solution hoặc layer đã lưu; tổng loại component; so sánh Jinja2. Thống nhất thuật ngữ với skill deploy/verify hiện có mà không gọi PAC write.
- **MVP:** Tóm tắt số đếm component và layer sở hữu cho một DEV solution unmanaged so với một export baseline.
- **Nghiên cứu:** Loại component nào churn nhiều nhất giữa hai snapshot?
- **Đánh giá:** Số đếm đồng thuận với Solution Packager hoặc PAC list trên một mẫu và bucket "không rõ" rõ ràng cho loại chưa ánh xạ.

### HY5. Bộ kiểm tra plugin step so với đăng ký trong source (M)

- **Tech stack đề xuất:** Python hoặc PowerShell so sánh export plugin-step đã lưu với thuộc tính được khai báo trong source (thuộc tính `CrmPluginRegistration` hoặc DevKit JSON); CSV các mismatch; pytest fixture.
- **MVP:** Với một assembly, báo cáo các step có trong export môi trường nhưng thiếu khai báo trong source, và ngược lại.
- **Nghiên cứu:** Mismatch bao nhiêu lần là đăng ký legacy cố ý so với drift thật?
- **Đánh giá:** Precision trên một assembly mentor gắn nhãn và xử lý rõ ràng tên step động. Chỉ-đọc; sửa đăng ký thuộc chủ sở hữu plugin.

---

## Danh sách khởi đầu đề xuất cho Wave-2

Chỉ là phán đoán kế hoạch. Xác nhận module, fixture và năng lực mentor trước khi phân công.

| Lĩnh vực | Lựa chọn đầu tiên | Lý do bắt đầu từ đây | Phương án nghiên cứu thay thế |
| --- | --- | --- | --- |
| Chất lượng dữ liệu | DQ5: Lệch ngày UserLocal | Đã có fixture PROD được tài liệu hóa | DQ2: Nhất quán VIN |
| Độ tin cậy tích hợp | IR2: Tóm tắt lỗi interface log | Log offline và baseline triage rõ ràng | IR1: Snapshot hợp đồng payload |
| Quyền riêng tư và truy cập | PA1: Lint PII tập dữ liệu | Bảo vệ file vàng trước khi commit | PA2: Allowlist trường log |
| Bản địa hóa | LG2: Kiểm tra drift glossary | Chỉ dùng tài liệu được track | LG1: Kiểm kê nhãn chưa dịch |
| Dẫn đường tri thức | KN1: Kiểm tra trích dẫn skill | Nhanh, chỉ-đọc, tín hiệu cao cho repo này | KN4: Độ tươi runbook |
| Phân tích quy trình | WA1: Snapshot tuổi work-order | Một export cho ra biểu đồ để duyệt | WA3: Pareto từ chối bảo hành |
| Vệ sinh client/solution | HY1: Kiểm kê Xrm.WebApi | Một thư mục, parse tất định | HY2: Bản đồ thứ tự form onload |

**Ghép cặp quan tâm tùy chọn (chỉ thảo luận):** Trần An Thắng có thể khám phá KN2 hoặc PA5; Trần Trung Hiếu có thể khám phá WA3 hoặc DQ1; Trần Huy Hoàng có thể khám phá IR2 hoặc IR5; Lê Trung Hiếu có thể khám phá HY5 hoặc PA2. Những ghép này không thay đổi phân công chính.

Để demo Wave-2 chung, nối **DQ5 → LG4 → PA1**: phát hiện lệch ranh giới ngày, khóa unit test định dạng locale, rồi lint tập dữ liệu hỗ trợ để tìm PII trước khi chia sẻ.
