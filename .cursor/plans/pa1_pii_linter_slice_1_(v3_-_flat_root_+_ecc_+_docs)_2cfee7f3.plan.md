---
name: PA1 PII Linter Slice 1 (v3 - flat root + ECC + docs)
overview: Tạo Python package PA1 PII Linter ở root repo (flat layout), bổ sung docs đầy đủ (architecture, contributing, detectors, spec, user-guide, problem), onboard project theo ECC (CLAUDE.md, AGENTS.md, .claude/rules) + cài ECC hook profile standard để enforce quy trình.
todos:
  - id: move-typo-files
    content: git mv environment.yml + pyproject.toml từ docs/problem/PA1/ về root; rmdir 3 sub-dir rỗng
    status: pending
  - id: verify-env-pa1
    content: Verify env pa1 vẫn hoạt động: conda activate pa1 + which python
    status: pending
  - id: core-package-init
    content: Tạo pii_linter/__init__.py + severity.py + suppressions.py + suppressions.yaml ở root
    status: pending
  - id: detectors-impl
    content: Tạo pii_linter/detectors/{__init__,column_name,content_regex,luhn_card,free_text}.py
    status: pending
  - id: report-impl
    content: Tạo pii_linter/report.py (render_markdown + mask_value)
    status: pending
  - id: cli-guard-impl
    content: Tạo pii_linter/cli.py + guard.py (2 subcommand, env check)
    status: pending
  - id: fixture-gen
    content: Tạo fixtures/generators/make_synthetic.py (Faker vi_VN, seed=42)
    status: pending
  - id: precommit-files
    content: Tạo .pre-commit-hooks.yaml + examples/pre-commit-config.yaml
    status: pending
  - id: tests-impl
    content: Tạo tests/{__init__,test_column_name,test_content_regex,test_luhn_card,test_guard,test_smoke}.py
    status: pending
  - id: gitignore-root
    content: Tạo .gitignore ở root (ignore fixtures/gold, __pycache__, .pytest_cache)
    status: pending
  - id: readme-root
    content: Tạo README.md ở root (2 personas + troubleshooting) — NGẮN, link sang docs/
    status: pending
  - id: docs-architecture
    content: Tạo docs/architecture.md (kiến trúc package + mermaid data-flow diagram)
    status: pending
  - id: docs-contributing
    content: Tạo docs/contributing.md (cách thêm detector/entity mới, thêm test, chạy smoke)
    status: pending
  - id: docs-detectors
    content: Tạo docs/detectors.md (API reference từng detector, regex, Luhn, suppressions)
    status: pending
  - id: docs-spec
    content: Tạo docs/spec.md (public API: dataclass + hàm, CLI flags, exit codes)
    status: pending
  - id: docs-user-guide
    content: Tạo docs/user-guide.md (cài đặt, suppressions, pre-commit, FAQ/troubleshooting)
    status: pending
  - id: docs-problem-pa1-md
    content: Tạo docs/problem/PA1/PA1.md tóm tắt vấn đề + link side.md/side.vi.md
    status: pending
  - id: ecc-onboard
    content: Onboard project qua ECC: chạy `npx ecc-universal setup --mode claude-plugin --scope project --hooks standard --yes`; tạo CLAUDE.md + AGENTS.md ở root
    status: pending
  - id: ecc-rules
    content: Tạo .claude/rules/{pii-guard,no-commit-gold,conda-env-pa1}.md cho AI agent biết workflow
    status: pending
isProject: false
---

# PA1 PII Linter — Slice 1 (v3, flat root + ECC + docs)

## Vấn đề kiến trúc đã sửa
Plan cũ nhét toàn bộ code vào `docs/problem/PA1/` — sai vì `docs/problem/` là nơi chứa tài liệu nghiên cứu (đã có `side.md`, `side.vi.md`). Slice 1 v3 dùng **flat root layout** chuẩn Python, bổ sung **docs đầy đủ** (5 file) và **onboard project theo ECC** (CLAUDE.md, AGENTS.md, rules, hook profile standard).

## Cấu trúc thư mục đích

```
vn-pii/                                              # repo root
├── README.md                                        # mô tả ngắn, 2 personas, link sang docs/
├── CLAUDE.md                                        # ECC: context cho Claude/Cursor khi làm việc với repo
├── AGENTS.md                                        # ECC: hướng dẫn cho AI agent (guard workflow, quy tắc commit)
├── pyproject.toml                                   # package metadata + entry point `pa1-lint`
├── environment.yml                                  # conda env `pa1` python=3.11
├── .pre-commit-hooks.yaml                           # pre-commit framework hook defs
├── .gitignore                                       # ignore fixtures/gold/*.csv, __pycache__/, .pytest_cache/
├── suppressions.yaml                                # mẫu suppressions có owner + expires_at
├── pii_linter/                                      # package chính
│   ├── __init__.py                                  # __version__ = "0.1.0"
│   ├── cli.py                                       # entry: `pa1-lint scan` + `pa1-lint guard -- <cmd>`
│   ├── guard.py                                     # subcommand guard: diff + scan pre/post
│   ├── severity.py                                  # LOW/MEDIUM/HIGH/CRITICAL + SEVERITY_BY_ENTITY + apply_combo_boost
│   ├── suppressions.py                              # load_suppressions(path) + is_suppressed(col, val, sups)
│   ├── report.py                                    # render_markdown(scan_result) + mask_value(value, entity)
│   └── detectors/
│       ├── __init__.py
│       ├── column_name.py                           # COLUMN_RULES heuristic
│       ├── content_regex.py                         # RE_VN_PHONE/CCCD/CMND/email/VIN/plate/zalo
│       ├── luhn_card.py                             # luhn_check + detect_card
│       └── free_text.py                             # full-scan note > 30 ký tự + combo boost
├── tests/
│   ├── __init__.py
│   ├── test_column_name.py
│   ├── test_content_regex.py
│   ├── test_luhn_card.py
│   ├── test_guard.py                                # test guard wrap + fail-fast
│   └── test_smoke.py                                # end-to-end trên fixture
├── fixtures/
│   ├── generators/
│   │   └── make_synthetic.py                        # Faker vi_VN, seed=42
│   ├── gold/                                        # .gitignore (không commit)
│   │   ├── leads_50.csv
│   │   ├── contracts_50.csv
│   │   ├── service_50.csv
│   │   ├── finance_50.csv
│   │   ├── notes_50.jsonl
│   │   └── report_sample.md
│   ├── negative/                                    # commit được
│   │   ├── crm_pipeline_50.csv
│   │   └── aggregate_50.csv
│   ├── seeds/README.md
│   └── README.md
├── examples/
│   └── pre-commit-config.yaml                       # mẫu copy vào repo user
├── docs/                                            # tài liệu (tách khỏi docs/problem/)
│   ├── architecture.md                              # kiến trúc + mermaid data-flow
│   ├── contributing.md                              # cách mở rộng
│   ├── detectors.md                                 # API reference từng detector
│   ├── spec.md                                      # public API + CLI flags + exit codes
│   ├── user-guide.md                                # cài đặt + suppressions + pre-commit + FAQ
│   └── problem/PA1/PA1.md                           # tóm tắt vấn đề (liên kết side.md/side.vi.md)
└── .claude/                                         # ECC: rules cho AI agent
    ├── rules/
    │   ├── pii-guard.md                             # rule: agent phải gọi `pa1-lint guard` trước khi sửa CSV/JSONL
    │   ├── no-commit-gold.md                        # rule: cấm commit fixtures/gold/*.csv
    │   └── conda-env-pa1.md                         # rule: luôn activate env `pa1` trước khi chạy tool
    └── settings.json                                # ECC config (nếu cần)
```

## Bước 0a — Di chuyển file đã tạo nhầm chỗ

- `git mv docs/problem/PA1/environment.yml ./environment.yml`
- `git mv docs/problem/PA1/pyproject.toml ./pyproject.toml`
- `rmdir docs/problem/PA1/{fixtures,pii_linter,tests}/` (3 sub-dir rỗng)
- Xác nhận `docs/problem/PA1/` còn trống, sẽ chứa `PA1.md` ở bước cuối.

## Bước 0b — Verify conda env `pa1`

- Env đã tạo ở phiên trước (`/home/tts/miniconda3/envs/pa1/`, python=3.11, đã cài Faker/pyyaml/pandas/pytest).
- `conda activate pa1 && which python` phải trỏ tới `envs/pa1/bin/python`.

## Bước 1 — Core package: `pii_linter/__init__.py` + `severity.py` + `suppressions.py` + `suppressions.yaml`

- `pii_linter/__init__.py`: `__version__ = "0.1.0"`.
- `pii_linter/severity.py`: hằng số `LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4`; `SEVERITY_BY_ENTITY = {PERSON: HIGH, PHONE: HIGH, EMAIL: MEDIUM, ID_NUMBER: HIGH, ACCOUNT_NO: HIGH, CARD_NO: CRITICAL, ASSET: MEDIUM, NOTE: MEDIUM, URL_HANDLE: MEDIUM}`; `COMBO_THRESHOLD=2, COMBO_BUMP=1`; dataclass `SeverityCount`; hàm `apply_combo_boost(by_entity) -> int`.
- `pii_linter/suppressions.py`: dataclass `Suppression(column_pattern, value_prefix, owner, expires_at, reason)` với method `matches(column, value, today)`; `load_suppressions(path)` parse YAML, trả `[]` nếu file không tồn tại; `is_suppressed(col, val, sups, today=None)`.
- `suppressions.yaml` ở root: 3 entry mẫu (customer_id → id_, phone/email → dummy, account_no → 0).

## Bước 2 — `pii_linter/detectors/`

- `detectors/__init__.py`: package marker.
- `detectors/column_name.py`: bảng `COLUMN_RULES` dạng `[(regex, entity, default_severity)]` (8 rule Việt + Anh). Hàm `score_column(name) -> list[ColumnHint]` (dataclass `entity, severity`).
- `detectors/content_regex.py`: compile `RE_VN_PHONE, RE_CCCD, RE_CMND, RE_EMAIL, RE_VIN, RE_PLATE, RE_ZALO` tại module load. `scan_value(value, column_hints) -> list[Finding]` (dataclass `Finding(entity, severity, evidence_raw, evidence_masked, span)`).
- `detectors/luhn_card.py`: `luhn_check(pan) -> bool`; `detect_card(value) -> Finding | None` (RE 13–19 số + Luhn + BIN rút gọn Visa/MC/Amex/JCB). Severity = CRITICAL.
- `detectors/free_text.py`: chỉ kích hoạt nếu `len(value) > 30` hoặc column hint NOTE. Gọi `content_regex.scan_value` + áp dụng combo boost: ≥2 pattern HIGH+ → bump severity.

## Bước 3 — `pii_linter/report.py`

- Dataclass `ScanResult(findings, files_scanned, by_file)`.
- `mask_value(value, entity)`:
  - PERSON: `Nguyễn V*** A***` (giữ first letter + họ)
  - PHONE: `09****123` (giữ 2 đầu + 3 cuối)
  - CCCD/ID: `****-****-***-12` (giữ 2 cuối)
  - EMAIL: `n.g.u.y.e.n@domain` (giữ domain)
  - CARD: `****-****-****-1234` (giữ 4 cuối)
- `render_markdown(scan_result) -> str`: bảng `| file | line | column | entity | severity | evidence_masked | suggestion |`.

## Bước 4 — `pii_linter/cli.py` + `pii_linter/guard.py`

**`cli.py`**:
- Đầu file: fail-fast env check (`'pa1' not in sys.prefix and 'conda' not in sys.prefix` → in "Run `conda activate pa1` first" + `exit(3)`).
- `argparse` 2 subcommand: `scan` và `guard`.
- `pa1-lint scan <path> [--format markdown|json] [--suppressions path]`:
  - Quét đệ quy `.csv`, `.jsonl`, `.md` đến depth 3.
  - CSV: `csv.DictReader`. JSONL: parse JSON, tự đoán key "note" bằng `score_column`. MD: trích dòng dạng bảng.
  - Exit code: 0 nếu max severity ≤ MEDIUM, 1 nếu HIGH, 2 nếu CRITICAL.
- `pa1-lint guard -- <cmd>` → `guard.run(cmd)`.

**`guard.py`**:
- `run(cmd: list[str]) -> int`:
  - Pre-scan: `git diff HEAD` → trích dòng `+` → scan. Nếu có finding HIGH+ → in báo cáo masked + `return 2` (không chạy cmd).
  - Sạch: `subprocess.run(cmd)`; nếu exit ≠ 0 → `return cmd_exit`.
  - Post-scan: lại `git diff HEAD` → scan → so sánh `evidence_masked` với pre-scan; nếu có finding mới → in báo cáo + `return 2`.
- Không phải git repo: in cảnh báo + skip guard (return 0).

## Bước 5 — `fixtures/generators/make_synthetic.py`

- `Faker("vi_VN")` + `Faker("en_US")`, seed=42.
- 7 hàm: `make_leads(50)`, `make_contracts(50)`, `make_service(50)`, `make_finance(50)`, `make_notes(50)`, `make_negative_crm(50)`, `make_negative_aggregate(50)`.
- Helper `make_card_luhn(prefix)` tự tính checksum cho Visa (4xx) / MC (5xx).
- Helper `make_vin()` 17 ký tự, loại I/O/Q.
- Output CSV/JSONL bằng stdlib (`csv.writer`, `json.dump`).
- CLI: `python fixtures/generators/make_synthetic.py --out fixtures/gold fixtures/negative`.

## Bước 6 — `.pre-commit-hooks.yaml` + `examples/pre-commit-config.yaml`

**`.pre-commit-hooks.yaml`** ở root:
```yaml
- id: pa1-lint-staged
  name: PA1 PII linter (staged files)
  description: Quét CSV/JSONL/Markdown staged để phát hiện PII trước khi commit
  entry: pa1-lint scan
  language: system
  pass_filenames: true
  types: [csv, jsonl, markdown]
```

**`examples/pre-commit-config.yaml`**: mẫu user copy vào repo của họ (3 dòng `repo: local` + entry `pa1-lint scan`).

## Bước 7 — Tests (`tests/`)

- `test_column_name.py`: `score_column("customer_phone")` → hint PHONE/HIGH; `score_column("qty")` → `[]`.
- `test_content_regex.py`: RE match `0912345678`, `012345678901`, `test@example.com`, `1HGCM82633A004352`, `30A-123.45`.
- `test_luhn_card.py`: `luhn_check("4111111111111111")` True; `detect_card("4111-1111-1111-1111")` → Finding CARD_NO/CRITICAL; `detect_card("1234567890123456")` → None.
- `test_guard.py`: repo git tạm + staged SĐT → `guard.run(["echo","ok"])` return 2, `echo` không chạy.
- `test_smoke.py`: CLI trên `fixtures/gold/leads_50.csv` (≥1 PHONE), `fixtures/negative/aggregate_50.csv` (0 finding), `fixtures/gold/finance_50.csv` (≥1 CARD_NO).

## Bước 8 — `.gitignore` ở root

```
fixtures/gold/*.csv
fixtures/gold/*.jsonl
__pycache__/
*.egg-info/
.pytest_cache/
.claude/settings.json
```

## Bước 9 — `README.md` ở root (NGẮN, link sang docs/)

**Persona A — Contributor**:
1. `conda env create -f environment.yml && conda activate pa1`
2. `pip install -e .[dev]`
3. `python fixtures/generators/make_synthetic.py --out fixtures/gold fixtures/negative`
4. `pa1-lint scan fixtures/gold`
5. `pytest tests/`

**Persona B — User cuối**:
1. `conda create -n pa1 python=3.10 -y && conda activate pa1 && pip install pa1-pii-linter` (slice 1: `pip install -e .` từ local)
2. Copy `examples/pre-commit-config.yaml` vào repo user
3. `pip install pre-commit && pre-commit install`
4. Từ giờ mỗi `git commit` tự động quét, dừng nếu PII
5. Wrap AI agent: `pa1-lint guard -- <cmd>`

**Cảnh báo:** fixture là synthetic; báo cáo chỉ hiển thị evidence đã mask.

**Troubleshooting:** link sang `docs/user-guide.md#troubleshooting`.

**Liên kết tài liệu đầy đủ:** `docs/architecture.md`, `docs/contributing.md`, `docs/detectors.md`, `docs/spec.md`, `docs/user-guide.md`, `docs/problem/PA1/PA1.md`.

## Bước 10 — Docs (5 file mới)

**`docs/architecture.md`** (~80 dòng):
- Mục đích & nguyên tắc (local-only, fail-fast, mask trước khi in).
- Mermaid diagram data-flow: `CSV/JSONL/MD` → `load_files()` → mỗi value → `score_column()` + `scan_value()` + `detect_card()` + `detect_free_text()` → `Finding[]` → `apply_combo_boost()` → `mask_value()` → `render_markdown()`.
- Mermaid diagram guard flow: `pa1-lint guard -- CMD` → pre-scan diff → nếu HIGH+ → exit 2; nếu sạch → chạy CMD → post-scan diff → nếu có finding mới → exit 2.
- Layered design: detectors (pure) → orchestrator (cli.py) → reporters.

**`docs/contributing.md`** (~60 dòng):
- Cách thêm detector mới: tạo `pii_linter/detectors/<name>.py` với hàm `detect(value, column_hints) -> list[Finding]`; thêm entry vào `SEVERITY_BY_ENTITY`; thêm test trong `tests/test_<name>.py`.
- Cách thêm entity mới: thêm key vào `SEVERITY_BY_ENTITY`; nếu cần regex mới → thêm `RE_*` vào `content_regex.py`.
- Cách chạy smoke: `pytest tests/ -v`.
- Style guide: dataclass cho DTO; docstring mô tả regex + đầu vào/ra; KHÔNG in raw PII ra log/print.

**`docs/detectors.md`** (~100 dòng):
- API reference cho `column_name.score_column(name)`, `content_regex.scan_value(value, hints)`, `luhn_card.detect_card(value)`, `free_text.scan(value, hints)`.
- Regex table: `RE_VN_PHONE` (đầu số VN 2025), `RE_CCCD` (12 số đầu 0), `RE_CMND` (9 số, chỉ khi hint ID_NUMBER), `RE_EMAIL`, `RE_VIN` (17 ký tự, loại I/O/Q), `RE_PLATE` (30A-123.45), `RE_ZALO` (zalo.me/ID).
- Luhn: spec ISO/IEC 7812, BIN table rút gọn (Visa 4, MC 5, Amex 3, JCB 35).
- Suppressions: cú pháp YAML, ví dụ 3 entry mẫu.

**`docs/spec.md`** (~80 dòng):
- Public API: dataclass `Finding`, `ColumnHint`, `Suppression`, `ScanResult` (field + type).
- Hàm public: `severity.apply_combo_boost()`, `report.mask_value()`, `report.render_markdown()`, `suppressions.load_suppressions()`, `suppressions.is_suppressed()`.
- CLI flags: `pa1-lint scan <path> [--format {markdown,json}] [--suppressions <path>]`; `pa1-lint guard -- <cmd>...`.
- Exit codes: 0 = clean, 1 = HIGH, 2 = CRITICAL, 3 = env not pa1.

**`docs/user-guide.md`** (~120 dòng):
- Cài đặt (Persona B).
- Suppressions YAML format + ví dụ + best practice (KHÔNG suppress dữ liệu thật).
- Pre-commit hook setup.
- Wrap AI agent bằng `pa1-lint guard`.
- FAQ:
  - `pa1-lint: command not found` → `pip install -e .` chưa chạy.
  - `pa1-lint: not running in conda env 'pa1'` → `conda activate pa1`.
  - Pre-commit hook không chạy → `git config core.hooksPath` không nên trỏ ra ngoài.
  - False positive trên cột `customer_id` chứa `id_001` → thêm suppression với `value_prefix: "id_"`.

## Bước 11 — `docs/problem/PA1/PA1.md`

~30 dòng, tóm tắt vấn đề:
- Tại sao cần detect PII pre-commit.
- Phạm vi slice 1: SĐT/CCCD/CMND/email/VIN/plate/zalo/card Luhn, scan CSV/JSONL/MD.
- Ngoài slice 1: precision/recall, cross-file, Presidio, SARIF, PyPI.
- Liên kết: `side.md`, `side.vi.md` (research đầy đủ); `docs/architecture.md`; `README.md`.

## Bước 12 — ECC onboarding

**12.1 — Cài ECC vào Cursor scope (project):**
- Dùng skill `configure-ecc` của ECC: chạy `npx ecc-universal setup --mode claude-plugin --scope project --hooks standard --yes`.
- Kết quả: `.claude/` được tạo với `settings.json` + rule defaults.

**12.2 — Tạo `CLAUDE.md` ở root** (~50 dòng):
- Project overview: PA1 PII Linter là local pre-commit scanner cho dataset VN.
- Build commands: `pip install -e .[dev]`, `python fixtures/generators/make_synthetic.py`, `pa1-lint scan`, `pytest`.
- Architecture summary: detectors → orchestrator → reporters.
- Conventions: dataclass, mask trước khi in, không commit `fixtures/gold/*.csv`.
- Key files: `pyproject.toml`, `pii_linter/cli.py`, `pii_linter/detectors/`, `tests/`.

**12.3 — Tạo `AGENTS.md` ở root** (~40 dòng):
- Hướng dẫn AI agent:
  - Luôn `conda activate pa1` trước khi chạy tool.
  - Trước khi edit file `.csv`/`.jsonl` → chạy `pa1-lint guard -- <edit-command>` để tránh leak PII.
  - Không commit `fixtures/gold/*.csv` (đã `.gitignore`).
  - Khi thêm detector mới → thêm entry vào `SEVERITY_BY_ENTITY` + test trong `tests/`.
- Reference: `docs/contributing.md`, `.claude/rules/`.

## Bước 13 — `.claude/rules/`

**`.claude/rules/conda-env-pa1.md`**:
- Trigger: khi agent chạy `pa1-lint`, `pytest`, hoặc script trong `fixtures/`.
- Action: kiểm tra `sys.prefix` có chứa `pa1` không; nếu không → chạy `conda activate pa1 && <cmd>` hoặc báo lỗi.

**`.claude/rules/no-commit-gold.md`**:
- Trigger: khi agent thực hiện `git add` hoặc `git commit`.
- Action: cảnh báo nếu file thuộc `fixtures/gold/*.csv` hoặc `fixtures/gold/*.jsonl` đang được add; từ chối commit, đề xuất `git restore --staged <file>`.

**`.claude/rules/pii-guard.md`**:
- Trigger: khi agent sửa file có đuôi `.csv`/`.jsonl`/`.md` ở ngoài `fixtures/negative/`.
- Action: bọc tool call bằng `pa1-lint guard -- <command>`; nếu guard exit ≠ 0 → rollback và cảnh báo.

## Điểm không thuộc slice 1
- Publish PyPI / conda-forge
- Cross-file correlation
- Presidio integration
- SARIF / GitHub Action
- Precision/recall đánh giá
- Wrapper chính thức cho Cursor/Aider/Claude Code (slice 1 chỉ cung cấp `pa1-lint guard`)

## Rủi ro & giảm thiểu
- 2 file đã tạo nhầm chỗ (`docs/problem/PA1/environment.yml`, `pyproject.toml`) — `git mv` về root trước khi sửa.
- 3 sub-dir rỗng `docs/problem/PA1/{fixtures,pii_linter,tests}/` — `rmdir` sau khi move.
- Pre-commit hook chậm — `pass_filenames: true` + `types: [csv, jsonl, markdown]` chỉ scan file staged.
- Faker locale vi_VN thiếu CCCD generator — tự viết helper.
- Regex SĐT rộng — ưu tiên column hint.
- Fixture gold không commit — `.gitignore` chỉ che `fixtures/gold/*.csv` + `*.jsonl`, vẫn commit `negative/` cho CI test.
- ECC setup interactive — dùng `--yes` để chạy non-interactive.
- ECC hook profile `standard` có thể ép formatter (black/ruff) — nếu code style khác, switch sang `minimal`.

## Tiêu chí hoàn thành
- `pa1-lint --version` in `0.1.0` trong env `pa1`.
- `pa1-lint scan fixtures/gold/leads_50.csv` in báo cáo Markdown, exit code 1.
- `pa1-lint scan fixtures/negative/aggregate_50.csv` in "no findings", exit 0.
- `pa1-lint guard -- echo ok` trong repo sạch → exit 0, `ok` được in.
- `pa1-lint guard -- echo ok` trong repo có staged SĐT → exit 2, `ok` không được in.
- `pytest tests/` pass tất cả.
- `.pre-commit-hooks.yaml` hợp lệ (parse YAML được).
- 5 file docs (`docs/architecture.md`, `contributing.md`, `detectors.md`, `spec.md`, `user-guide.md`) + `docs/problem/PA1/PA1.md` đầy đủ.
- `CLAUDE.md` + `AGENTS.md` + 3 file `.claude/rules/` cho AI agent.
- `npx ecc-universal doctor --target cursor` (hoặc tương đương) báo OK.
