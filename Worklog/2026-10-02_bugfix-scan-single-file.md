# 2026-10-02 — Fix `_list_files` single-file path

## Context

- **Session:** Verify Slice 1 hoàn thành + fix bug phát hiện trong quá trình verify.
- **Trigger:** User hỏi "Tiếp theo nên làm gì" → kiểm tra plan v3 → phát hiện 4 acceptance test trong plan §Tiêu chí hoàn thành có 1 test (`pa1-lint scan fixtures/gold/leads_50.csv`) đang fail với `exit 0, files_scanned: 0`.

## Đã làm

- **Verify**: chạy `pa1-lint scan fixtures/gold/leads_50.csv` → exit 0, 0 findings (kỳ vọng: exit 1, ≥1 PHONE).
- **Root cause**: `_list_files(root)` ở `pii_linter/cli.py:55–63` gọi `root.rglob('*')`; khi `root` là file (không phải directory), `rglob` trả về 0 mục → CLI thấy không có file để scan.
- **Patch**: Thêm 4 dòng early-return khi `root.is_file()` (chỉ yield nếu suffix nằm trong `{csv,jsonl,md}`). Logic `rglob` cho directory giữ nguyên.

```python
# pii_linter/cli.py — _list_files()
if root.is_file():
    if root.suffix.lower() in _TARGET_EXTS:
        yield root
    return
base_depth = len(root.parts) - 1
...
```

- **Bonus discovery**: 5 docs file (`docs/architecture.md`, `contributing.md`, `detectors.md`, `spec.md`, `user-guide.md`) đều **đã có** từ trước → plan v3 §10 thực ra đã hoàn thành. Chỉ thiếu layer navigation (PLAN/Worklog/Index).
- **Tạo layer navigation**: `PLAN.md`, `Worklog/INDEX.md`, file này, `Index.md` (root).

## Findings / decisions

- **`rglob` không yield self**: Python `Path.rglob('*')` trên file path rỗng — đây là hành vi well-documented nhưng dễ bị miss. Cần test edge case này.
- **Plan v3 status `pending` không phản ánh thực tế**: 17 todo trong plan đa số đã xong từ session trước, chỉ thiếu navigation. → Không nên skip verification; luôn `ls` trước.
- **Bug xuất hiện ở CLI layer, không phải detector**: detector đã đúng (JSONL scan ra 364 findings), chỉ CLI không enumerate được file đơn. → Đó là lý do chỉ fix `_list_files`, không cần động vào `detectors/`.

## Acceptance

- [x] `pa1-lint scan fixtures/gold/leads_50.csv` → exit 1, 100 findings (50 PHONE + 50 EMAIL)
- [x] `pa1-lint scan fixtures/gold/notes_50.jsonl` → exit 2, 364 findings (CRITICAL)
- [x] `pa1-lint scan fixtures/negative/aggregate_50.csv` → exit 0, 0 findings
- [x] `pa1-lint scan fixtures/gold/` (directory) → vẫn chạy `rglob` như cũ
- [x] `pytest tests/test_smoke.py -v` → 4 passed
- [x] Plan v3 §Tiêu chí hoàn thành 7/7 pass

## Outstanding

- Không — slice 1 đã hoàn thành. Out-of-scope vẫn đúng (cross-file, Presidio, SARIF, PyPI).

## Liên kết

- [`PLAN.md`](../../PLAN.md) §Tiêu chí hoàn thành
- [`docs/architecture.md`](../../docs/architecture.md) §Layered design
- File đã patch: `pii_linter/cli.py` `_list_files()` (line 55–63)