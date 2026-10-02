# PLAN.md — PA1 PII Linter (Slice 1)

> **Bản rút gọn của [`.cursor/plans/pa1_pii_linter_slice_1_(v3_-_flat_root_+_ecc_+_docs)_2cfee7f3.plan.md`](.cursor/plans/pa1_pii_linter_slice_1_(v3_-_flat_root_+_ecc_+_docs)_2cfee7f3.plan.md)**
>
> File này là **single source of truth** cho mục tiêu và scope dự án.
> Plan chi tiết theo từng todo step ở trong `.cursor/plans/`.

## Đích đến (Goal)

Cung cấp một scanner PII tiếng Việt **chạy local, không phụ thuộc dịch vụ ngoài**, có thể:

1. **Pre-commit gate**: chặn CSV/JSONL/Markdown chứa PII Việt trước khi vào repo.
2. **AI-agent wrapper**: chặn tool call của AI agent nếu nó sẽ tạo ra/leak PII.

## Phạm vi Slice 1 (MVP)

| Thành phần | Mô tả |
|---|---|
| Entities | `PHONE`, `ID_NUMBER` (CCCD/CMND), `EMAIL`, `CARD_NO` (Luhn), `ASSET` (VIN/plate), `URL_HANDLE` (zalo.me), `NOTE` (free-text combo), `PERSON` (column hint) |
| Detectors | `column_name`, `content_regex`, `luhn_card`, `free_text` |
| File formats | `.csv`, `.jsonl`, `.md` (bảng) |
| CLI | `pa1-lint scan <path>`, `pa1-lint guard -- <cmd>` |
| Output | Markdown (default) hoặc JSON |
| Severity | LOW / MEDIUM / HIGH / CRITICAL + exit code 0/1/2/3 |
| Suppressions | YAML với `column_pattern`, `value_prefix`, `owner`, `expires_at` |
| Pre-commit | `.pre-commit-hooks.yaml` ở root, copy-paste qua `examples/` |
| Env | `pa1` conda env (Python 3.11) |

## Ngoài-scope (Slice 1 **không** bao gồm)

- ❌ Cross-file correlation
- ❌ Presidio integration
- ❌ SARIF / GitHub Action
- ❌ Precision/recall evaluation
- ❌ Publish lên PyPI / conda-forge
- ❌ Wrapper chính thức cho Cursor/Aider/Claude Code (slice 1 chỉ có `pa1-lint guard`)

## Layout đích

```
vn-pii/
├── PLAN.md                   ← file này: goal + scope + out-of-scope
├── INDEX.md                  ← navigation graph cho AI agent
├── CLAUDE.md                 ← pointer ngắn → AGENTS.md + PLAN + INDEX + Worklog
├── AGENTS.md                 ← workflow rules cho AI agent
├── README.md                 ← 2 personas (contributor / user)
├── pyproject.toml            ← package + entry point `pa1-lint`
├── environment.yml           ← conda env `pa1` python=3.11
├── .pre-commit-hooks.yaml    ← hook cho repo khác dùng
├── suppressions.yaml         ← mẫu suppressions
├── pii_linter/               ← package chính
├── tests/                    ← pytest suite
├── fixtures/{gold,negative}/ ← synthetic data (gold git-ignored)
├── Worklog/                  ← 1 file mỗi session, ghi bug fix / decisions
├── docs/                     ← architecture, contributing, detectors, spec, user-guide, problem
└── .claude/rules/            ← auto-applied rules per file type
```

## Tiêu chí hoàn thành Slice 1

- [x] `pa1-lint --version` in `0.1.0` trong env `pa1`
- [x] `pa1-lint scan fixtures/gold/leads_50.csv` → exit 1, ≥1 PHONE finding
- [x] `pa1-lint scan fixtures/negative/aggregate_50.csv` → exit 0, 0 finding
- [x] `pa1-lint scan fixtures/gold/notes_50.jsonl` → exit 2 (CRITICAL), ≥1 CARD_NO
- [x] `pytest tests/` pass tất cả
- [x] `.pre-commit-hooks.yaml` parse YAML hợp lệ
- [x] 5 file docs + `docs/problem/PA1/PA1.md`
- [x] `CLAUDE.md` + `AGENTS.md` + 3 file `.claude/rules/`

## Cách dùng PLAN.md

| Bạn muốn | Đọc |
|---|---|
| Hiểu project đang hướng về đâu | File này |
| Xem từng todo step đã/đang làm | `.cursor/plans/<plan-id>.plan.md` |
| Biết session nào đã qua, fix gì | `Worklog/INDEX.md` |
| Hiểu kiến trúc package | `docs/architecture.md` |
| Thêm detector / entity | `docs/contributing.md` |
| Cài / troubleshoot | `docs/user-guide.md` |