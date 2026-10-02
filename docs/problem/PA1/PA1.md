### PA1. Dataset PII linter (S)

- **Recommended tech stack:** Python CLI, regex and column-name heuristics, optional `presidio-analyzer` if approved for the workstation; pytest fixtures with planted PII; exit codes for pre-commit or CI. Scan only paths the intern owns (golden JSONL, sample CSV).
- **MVP:** Flag likely names, phones, emails, national IDs and free-text blobs in one proposed golden dataset before it is committed, with a suppressions file for known synthetic fields.
- **Research:** Do column heuristics plus regex beat regex-alone on mentor-labelled columns?
- **Evaluate:** Precision/recall on planted PII, false alarms on synthetic IDs and time to clean a failing file. Never print full secret values in the report.

### PA1. Bộ lint PII tập dữ liệu (S)

- **Tech stack đề xuất:** CLI Python, regex và heuristic theo tên cột, tùy chọn `presidio-analyzer` nếu được duyệt cho workstation; pytest fixture với PII gieo sẵn; exit code cho pre-commit hoặc CI. Chỉ quét các đường dẫn thực tập sinh sở hữu (golden JSONL, CSV mẫu).
- **MVP:** Đánh dấu khả năng chứa tên, số điện thoại, email, CMND/CCCD và blob văn bản tự do trong một golden dataset dự kiến trước khi commit, kèm file suppressions cho các trường tổng hợp đã biết.
- **Nghiên cứu:** Heuristic cột cộng regex có thắng regex-đơn-lẻ trên các cột được mentor gắn nhãn không?
- **Đánh giá:** Precision/recall trên PII gieo sẵn, cảnh báo sai trên ID tổng hợp và thời gian dọn một file đang lỗi. Không bao giờ in nguyên giá trị bí mật trong báo cáo.