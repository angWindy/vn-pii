# INDEX.md — Navigation cho AI Agent

> **File này là entry point.** Agent mới vào repo (Cursor/Aider/Claude Code) đọc file này trước tiên để hiểu context.
>
> Thứ tự đọc: `CLAUDE.md` → **`INDEX.md`** (đây) → `AGENTS.md` → `PLAN.md` → `Worklog/INDEX.md` → entry document `docs/`.

## Repo flow tổng thể (mermaid)

```mermaid
flowchart TD
    User([User / Maintainer]) --> CLAUDE[CLAUDE.md<br/>context ngắn]
    User --> AGENTS[AGENTS.md<br/>workflow rules]
    User --> INDEX[INDEX.md<br/>file này]

    CLAUDE --> PLAN[PLAN.md<br/>goal + scope]
    INDEX --> PLAN
    INDEX --> WORKLOG[Worklog/INDEX.md<br/>catalog bug fix / decision]
    INDEX --> AGENTS
    INDEX --> DOCS[docs/<br/>architecture · contributing · detectors · spec · user-guide]
    INDEX --> SRC[pii_linter/<br/>package chính]
    INDEX --> TESTS[tests/<br/>pytest suite]
    INDEX --> FIX[fixtures/{gold,negative}/<br/>]

    AGENTS --> RULES[.claude/rules/<br/>pii-guard · no-commit-gold · conda-env-pa1]
    PLAN --> CURSOR[(.cursor/plans/<br/>plan snapshot chi tiết)]

    SRC --> CLI[cli.py · guard.py]
    CLI --> DET[detectors/<br/>column_name · content_regex · luhn_card · free_text]
    CLI --> RPT[report.py
    CLI --> SEV[severity.py
    CLI --> SP2[suppressions.py

    DOCS --> PROBLEM[docs/problem/PA1/PA1.md<br/>problem gốc + side.md]
    FIX --> GOLD[fixtures/gold/<br/>gitignored]
    FIX --> NEG[fixtures/negative/<br/>commit được]
```

## Mapping task → file

| Agent cần | Đọc |
|---|---|
| Hiểu project đang làm cái gì, scope thế nào | [`PLAN.md`](PLAN.md) |
| Workflow quy tắc (env, guard, không commit gold, …) | [`AGENTS.md`](AGENTS.md) |
| Bug đã fix gì, decision nào đã chốt | [`Worklog/INDEX.md`](Worklog/INDEX.md) |
| Session gần nhất sửa gì | File mới nhất trong `Worklog/` |
| Hiểu kiến trúc package + chunks flow | [`docs/architecture.md`](docs/architecture.md) |
| Cách thêm detector / entity mới | [`docs/contributing.md`](docs/contributing.md) |
| Regex + Luhn spec | [`docs/detectors.md`](docs/detectors.md) |
| Public API + CLI flags + exit codes | [`docs/spec.md`](docs/spec.md) |
| Cài / suppressions / pre-commit / FAQ | [`docs/user-guide.md`](docs/user-guide.md) |
| Problem statement gốc | [`docs/problem/PA1/PA1.md`](docs/problem/PA1/PA1.md) |
| Code entry point | `pii_linter/cli.py` |
| Thêm detector | `pii_linter/detectors/<name>.py` + update `severity.py` |
| Severity table | `pii_linter/severity.py` `SEVERITY_BY_ENTITY` |
| Suppressions format | `suppressions.yaml` + `pii_linter/suppressions.py` |
| Tests | `tests/test_*.py` |

## Quy tắc đọc (cho agent mới)

1. **Bắt buộc đọc trước khi sửa code:**
   - `CLAUDE.md` (1 lần)
   - `AGENTS.md` (1 lần)
   - file trong `Worklog/` có ngày ≥ hôm nay hoặc gần nhất
2. **Không đọc trừ khi cần:** docs chuyên biệt — chỉ đọc khi task thuộc phạm vi đó (ví dụ: thêm detector mới → đọc `docs/contributing.md`).
3. **Tạo worklog sau khi sửa xong:** mỗi session đều append 1 file vào `Worklog/` + 1 dòng vào `Worklog/INDEX.md`.
4. **Không đụng `fixtures/gold/`** (gitignored, chỉ hidden, không commit).

## Quy tắc sửa

| Trước khi sửa | Phải |
|---|---|
| Sửa `.csv` / `.jsonl` / `.md` ngoài `fixtures/negative/` | Wrap bằng `pa1-lint guard -- <edit-cmd>` |
| Chạy `pa1-lint` / `pytest` / script `fixtures/generators/` | `conda activate pa1` trước |
| Stage file trong `fixtures/gold/` | `git restore --staged <file>` |
| Thêm detector / entity mới | Thêm key vào `SEVERITY_BY_ENTITY` + test trong `tests/test_<name>.py` |
| Thêm dependency vào `pyproject.toml` | Hỏi user trước |
| Commit | Tạo 1 entry worklog trước |

## Liên kết ra ngoài

- Plan snapshot chi tiết: `.cursor/plans/pa1_pii_linter_slice_1_(v3_-_flat_root_+_ecc_+_docs)_2cfee7f3.plan.md`
- ECC rules: `.claude/rules/{pii-guard,no-commit-gold,conda-env-pa1}.md`