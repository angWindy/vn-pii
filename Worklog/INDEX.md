# Worklog Index

> **Mỗi session làm việc trên repo đều tạo 1 file `Worklog/YYYY-MM-DD_<topic>.md`**
> và append 1 dòng vào bảng dưới đây.
>
> Mục đích: agent session sau đọc lại biết **đã fix gì, vì sao, còn nợ gì**.

## Cách viết 1 entry worklog (template)

```markdown
# YYYY-MM-DD — <topic ngắn, ≤6 từ>

## Context
- Session: <mục tiêu ban đầu>
- Tại sao: <trigger — bug report / plan todo / user request>

## Đã làm
- **commit/file**: mô tảngắn
- **commit/file**: mô tảngắn

## Findings / decisions
- Phát hiện X → quyết định Y vì Z.

## Acceptance
- [x] N`pa1-lint scan fixtures/gold/leads_50.csv` → exit 1
- [x] N`pytest tests/ -v` → N test pass

## Outstanding
- Bug #2 chưa fix.
- Cần user quyết định approach v2 (scalar 1 / scalar 2).

## Liên kết
- PLAN.md §Tiêu chí hoàn thành
- docs/architecture.md §X
- PR #N / commit <hash>
```

## Cách dùng Worklog

| Agent cần | Đọc |
|---|---|
| Biết session gần nhất sửa gì | Entry mới nhất ở bảng dưới |
| Tìm bug đã fix để khỏi tái khám | `grep -ri "fix" tags/title/ Worklog/` |
| Biết còn outstanding gì | Filter bảng dưới — cột status |
| Tạo entry mới | Copy template trên, lưu `YYYY-MM-DD_<topic>.md`, append 1 dòng vào bảng dưới |

## Catalog

| Ngày | Topic | Trạng thái | File |
|---|---|---|---|
| 2026-10-02 | Fix `_list_files` không xử lý single-file path | ✅ done | [`2026-10-02_bugfix-scan-single-file.md`](2026-10-02_bugfix-scan-single-file.md) |