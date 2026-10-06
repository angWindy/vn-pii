# Wave-2 side-project and research bank

**Brainstorm added:** 23 September 2026. These 35 proposals supplement the first side-project bank; they are candidate experiments, not confirmed implementation gaps or measured benefits. They stay distinct from the July batch (user-guide RAG, Sales/Aftersales Playwright, EN/VN rewrite), projects 1–10, and UT/TC/AR/AU/OP. Prefer sanitized exports, saved metadata and local fixtures over live production writes.

Each MVP assumes one intern, one module or workflow, an available mentor and accessible sample data. **S** means an estimated 1–2 focused weeks; **M** means 3–4 focused weeks, excluding access delays and alongside-project scheduling. These are planning estimates, not delivery commitments.

---

## 1. Data quality: catch inconsistencies in master and transactional exports

Work from sanitized CSV/JSONL extracts and saved metadata dumps. Do not treat these pilots as a warehouse or as authority to correct live records.

### DQ1. Duplicate account candidate finder (M)

- **Recommended tech stack:** Python, pandas, a blocking key (for example normalized phone or tax code) plus rapidfuzz or scikit-learn string similarity; Streamlit for a mentor review queue; SQLite for labelled decisions; pytest for planted-duplicate fixtures.
- **MVP:** Rank candidate account pairs from one sanitized export with evidence fields and a reviewable accept/reject queue. Export a decision CSV with the scoring rule version.
- **Research:** Does blocking plus similarity find more true duplicates than exact-key matching at the same false-positive budget?
- **Evaluate:** Precision and recall on a mentor-labelled sample; review time per decision. Never auto-merge; keep merge suggestions advisory.

### DQ2. VIN and vehicle-master consistency checker (S)

- **Recommended tech stack:** Python, pandas and Pydantic models for VIN, model, color and status fields; pytest fixtures with planted mismatches; Jinja2 Markdown report.
- **MVP:** Compare one vehicle-information export against its linked product or model master and list conflicting attributes with record identifiers.
- **Research:** Which rule classes (missing, conflicting, impossible combination) dominate on a real extract?
- **Evaluate:** Rule precision against mentor adjudication and false alarms on known-good rows. Treat VIN checksum rules as optional and region-specific.

### DQ3. Cross-environment option-set diff (M)

- **Recommended tech stack:** Python, two saved Dataverse metadata exports (JSON or XML), Pydantic option-set models, deepdiff or a hand-written structural diff, Jinja2 HTML/Markdown. PAC or Web API pulls stay outside the MVP if exports already exist.
- **MVP:** Diff labels, values and state codes for option sets used by one agreed entity between DEV and UAT65 (or UAT65 and PROD) using saved exports only.
- **Research:** How often label-only drift appears without value drift, and does that confuse BA comparisons?
- **Evaluate:** Matching accuracy on a seeded export pair and mentor-confirmed actionable diffs. Report removed values separately from renamed labels.

### DQ4. Broken lookup sampler (S)

- **Recommended tech stack:** Python/pandas over a sanitized parent/child CSV pair; SQLite for orphan caches; Jinja2 summary. Prefer offline joins before any live Web API probe.
- **MVP:** For one parent/child relationship, sample child rows whose lookup points at a missing or inactive parent and produce a count plus exemplar IDs.
- **Research:** Are inactive-parent references materially different from hard orphans for the selected workflow?
- **Evaluate:** Spot-check correctness of the join and stability of counts across two extract dates. Cap sample size; avoid bulk live retrieves in the MVP.

### DQ5. User-local date mismatch detector (S)

- **Recommended tech stack:** Python, `zoneinfo`, pandas and pytest fixtures built from the documented warranty-history case in [warranty-history-userlocal-date-mismatch-2026-09-22.md](../power-apps/warranty-history-userlocal-date-mismatch-2026-09-22.md); Jinja2 for a short investigator report.
- **MVP:** Given paired raw UTC and UI DateOnly/UserLocal values for one attribute family, flag day-boundary mismatches and explain the timezone math with evidence fields.
- **Research:** Can a deterministic checker reproduce the known PROD mismatch and find similar pairs in a sanitized export?
- **Evaluate:** Detection of the planted fixture, zero false alarms on same-day cases, and clear evidence links. Keep remediation advisory; do not rewrite history tables in the pilot.

---

## 2. Integration reliability: inspect saved payloads and job evidence

Distinct from project 3 (live App Insights triage), AU2 (CI log classification) and TC5 (fault-injection unit suites). Start with offline artifacts.

### IR1. Outbound payload contract snapshot (M)

- **Recommended tech stack:** Python CLI, Pydantic or JSON Schema for one `Send*`-style outbound message, golden request/response JSONL, pytest contract tests, Jinja2 drift report. Prefer sanitized captured payloads over live SAP or MuleSoft calls.
- **MVP:** Freeze a schema for one outbound integration message and validate a folder of saved payloads, reporting missing fields, type mismatches and unexpected properties.
- **Research:** Does a schema snapshot catch more breaking field changes than informal field checklists on the same corpus?
- **Evaluate:** Precision on planted schema breaks and false alarms on legitimate optional fields. Version the schema beside the fixtures.

### IR2. Interface-log failure digest (S)

- **Recommended tech stack:** Python/pandas over a sanitized interface or Service Bus log export; regex plus TF-IDF clustering; Jinja2 digest; optional LLM client only for cluster titles after counts are computed.
- **MVP:** Summarize one day's failed interface rows by signature, volume, first/last seen and linked runbook candidates.
- **Research:** Do clustered digests reduce mentor triage time versus a raw failure CSV?
- **Evaluate:** Cluster purity on a labelled sample, unsupported claim rate if LLM titles are used, and digest generation time. Offline-only for the MVP.

### IR3. Idempotent callback replay (M)

- **Recommended tech stack:** C# or Python local fake matching the selected callback contract; deterministic duplicate-delivery script; SQLite side-effect ledger; pytest or xUnit assertions on create/update counts. Reuse DMS_LOCAL_HOST doubles when the handler already runs there.
- **MVP:** Replay one inbound callback with duplicate and out-of-order deliveries against a local fake and prove the intended side-effect count.
- **Research:** Which duplicate keys (message id, business key, correlation id) actually protect the handler under test?
- **Evaluate:** Correct side-effect counts, detectable double-writes and missing recovery paths. Keep real broker guarantees as a later suite, labelled separately.

### IR4. Hangfire job duration baseline (S)

- **Recommended tech stack:** Python/pandas over exported Hangfire or job-history CSV; percentiles with Plotly; Jinja2 weekly baseline. Prefer read-only exports from the DMS API host's job tables or saved dashboards.
- **MVP:** For one recurring job, chart duration percentiles over a fixed window and flag runs above an agreed threshold with the revision and data-size notes when available.
- **Research:** Does a simple percentile baseline surface regressions earlier than mean-only monitoring on the same series?
- **Evaluate:** Agreement with mentor-labelled slow runs and false-alarm rate. Document cold starts and dependency outages as separate categories.

### IR5. Retry-storm detector (S)

- **Recommended tech stack:** Python/pandas time-series over sanitized retry or dead-letter counters; sliding-window rules first; Streamlit optional for inspection.
- **MVP:** Detect bursts where the same interface retries exceed a threshold within a short window and emit a Markdown alert with top signatures.
- **Research:** How well do fixed windows separate storms from expected overnight backfills?
- **Evaluate:** Precision/recall on planted storms in historical series; abstain when volume is too low to judge. Pair with IR2 rather than replacing App Insights triage.

---

## 3. Privacy and access review: defensive checks only

These pilots review data and configuration. They do not grant elevated access, extract secrets or publish attack procedures.

### PII. Dataset PII linter (S)

- **Recommended tech stack:** Python CLI, regex and column-name heuristics, optional `presidio-analyzer` if approved for the workstation; pytest fixtures with planted PII; exit codes for pre-commit or CI. Scan only paths the intern owns (golden JSONL, sample CSV).
- **MVP:** Flag likely names, phones, emails, national IDs and free-text blobs in one proposed golden dataset before it is committed, with a suppressions file for known synthetic fields.
- **Research:** Do column heuristics plus regex beat regex-alone on mentor-labelled columns?
- **Evaluate:** Precision/recall on planted PII, false alarms on synthetic IDs and time to clean a failing file. Never print full secret values in the report.

### PA2. Log field allowlist checker (S)

- **Recommended tech stack:** C# Roslyn or regex scan over one plugin/API project; JSON allowlist of permitted log templates; pytest/xUnit for rule fixtures; Markdown findings. Align with the existing gitleaks and plugin secret-scan scripts as complementary gates.
- **MVP:** Flag `ILogger`/`Trace` statements that interpolate entity attributes outside an allowlist (for example passwords, tokens, full request bodies).
- **Research:** Does an allowlist reduce noise compared with blanket "no entity ToString" rules?
- **Evaluate:** Precision on historical leak-prone patterns and missed finds on a labelled sample. Start with one assembly.

### PA3. Security-role privilege explainer (M)

- **Recommended tech stack:** Python XML parser for one exported security role, Pydantic privilege models, Jinja2 narrative; optional LLM client that may only paraphrase fields already present in the XML. pytest checks that every claim cites a privilege node.
- **MVP:** Produce a human-readable privilege summary for one role (create/read/write/delete and append scope per table) with citations back to the export.
- **Research:** Does an LLM paraphrase help BAs faster than a structured table when hallucinations are blocked by citation checks?
- **Evaluate:** Claim-to-XML accuracy and BA usefulness scores. Reject any sentence that cannot point at a privilege row.

### PA4. Audit spike sampler (M)

- **Recommended tech stack:** Reuse patterns from the export-dataverse-audit-history skill; Python/pandas over one saved audit export; Plotly for volume by user and entity; Jinja2 summary. Read-only; no audit configuration changes.
- **MVP:** Summarize unusual audit volume for one entity over a fixed window with top users, operations and sample record IDs.
- **Research:** Which simple baselines (day-of-week median, rolling z-score) best match mentor "unusual" labels?
- **Evaluate:** Precision on planted spikes and explanation quality. Keep outputs inside mentor review; treat as investigative evidence only.

### PA5. RAG prompt-injection fixture pack (S)

- **Recommended tech stack:** Versioned JSONL fixtures, project 4 scorers, the shared LLM client and the target assistant's retrieval stub. Score whether answers stay faithful to retrieved documents and refuse out-of-scope instructions. Defensive evaluation only; do not publish exploit procedures or production-targeting payloads.
- **MVP:** A fixture pack of benign and adversarial user prompts for one RAG assistant, with pass/fail rubrics for citation fidelity and instruction hierarchy.
- **Research:** Which fixture classes most often cause citation loss or policy bypass on the selected assistant?
- **Evaluate:** Scorer agreement with mentor labels and regression detection when a prompt changes. Keep fixtures internal to the evaluation repo.

---

## 4. Localization and glossary: inventory gaps without owning the rewrite tool

The July EN/VN standardization project remains the rewrite owner. These ideas only inventory, diff and test.

### LG1. Untranslated label inventory (S)

- **Recommended tech stack:** Python over exported Dataverse localized-label JSON or solution XML; pandas; Jinja2 report. Scope to one entity or one solution.
- **MVP:** List attributes, views and option labels missing a Vietnamese or English localized value relative to the base language.
- **Research:** How often "missing" is actually an intentional reuse of the base string?
- **Evaluate:** Precision after mentor review of a sample and stability across two exports. Output an inventory CSV, not rewritten strings.

### LG2. Glossary drift checker (S)

- **Recommended tech stack:** Python, `markdown-it-py` to parse [glossary.md](../glossary.md), term extraction from one docs subtree, pytest for fixture glossaries, Jinja2 drift report.
- **MVP:** Find terms used in a selected docs folder that lack glossary entries, and glossary entries never referenced in that folder.
- **Research:** Does stemming or simple alias lists improve useful hits over exact match?
- **Evaluate:** Mentor-accepted new-term candidates and false alarms on code identifiers. Propose glossary patches; do not auto-edit the glossary in CI without review.

### LG3. Bilingual UI string parity report (M)

- **Recommended tech stack:** Python/pandas comparing EN and VN resource or label exports; length-ratio and placeholder-token checks; optional LLM client for semantic-similarity scores on a sample; Streamlit review.
- **MVP:** Report pairs where placeholders diverge, one side is empty or length ratios look extreme for one model-driven app area.
- **Research:** Do placeholder and length rules catch more BA-visible defects than semantic-similarity alone?
- **Evaluate:** Precision on planted defects and review time. Hand findings to the July standardization owners when rewrites are needed.

### LG4. Locale formatting unit tests (S)

- **Recommended tech stack:** C# or JavaScript unit tests around one pure date/number formatting helper; fixed culture fixtures; the module's existing test runner.
- **MVP:** Lock expected strings for ICT and a second culture for currency, DateOnly and DateTime displays used by one screen.
- **Research:** Which failures come from culture vs from UserLocal attribute behavior (pair with DQ5)?
- **Evaluate:** Failures caught when someone changes format providers and zero flaky culture dependencies on the agent machine. Keep tests deterministic with explicit cultures.

### LG5. User-facing error message catalog (M)

- **Recommended tech stack:** C# Roslyn or regex extraction from one plugin project; CSV/JSON catalog; optional LLM client to draft clearer user wording while preserving error codes; Jinja2 catalog page in DMS_DOCS style.
- **MVP:** Inventory thrown user-facing messages with code, source location and whether EN/VN variants exist.
- **Research:** How many messages are developer-only exceptions leaking to the UI?
- **Evaluate:** Catalog completeness on a sampled assembly and BA ratings of suggested rewrites. Suggestions remain proposals for owners of those plugins.

---

## 5. Knowledge navigation: pointers and clusters without full RAG platforms

Distinct from project 6 (multi-repo runbook assistant) and project 7 (executable FetchXML/SQL). Prefer links, indexes and offline clustering.

### KN1. Skill citation checker (S)

- **Recommended tech stack:** Node or Python Markdown/link crawler over `DMS_DOCS/.cursor/skills/**/SKILL.md` and referenced paths; pytest for broken-link fixtures; Markdown report.
- **MVP:** Verify that every relative path and skill reference in the skill tree resolves, and list skills with no inbound link from `AGENTS.md` or peer skills.
- **Research:** Do orphan skills correlate with stale instructions on a mentor-labelled sample?
- **Evaluate:** True broken links found, false positives on intentional external URLs and runtime under one minute for the tree. Read-only.

### KN2. Table-catalog relationship explainer (M)

- **Recommended tech stack:** Python over one entity page from `docs/power-apps/tables/uat65/`; Jinja2 explanation template; optional LLM client constrained to cite only fields and relationships present on that page; pytest citation checks.
- **MVP:** Produce a one-page BA explanation of one entity's key fields and relationships with anchors back to the catalog.
- **Research:** Does constrained generation beat a pure template for BA comprehension without inventing fields?
- **Evaluate:** Citation accuracy and BA usefulness. Fail the run if any named field is absent from the source page.

### KN3. Incident theme cluster (M)

- **Recommended tech stack:** Python, scikit-learn TF-IDF and clustering over `docs/solutions/incidents/` and selected performance notes; Streamlit cluster browser; JSONL labels.
- **MVP:** Cluster historical incident writeups into themes and map each cluster to existing runbooks or skills when a keyword match exists.
- **Research:** Do clusters surface themes that mentoring reviews would have grouped the same way?
- **Evaluate:** Mentor agreement on cluster labels and useful cross-links. Offline Markdown only; no Jira writes in the MVP.

### KN4. Runbook freshness report (S)

- **Recommended tech stack:** Python over Git history (`git log` porcelain) for `docs/runbooks/` and selected skills; pandas; Jinja2 aging report.
- **MVP:** List runbooks older than an agreed threshold since last content commit, with owners inferred from CODEOWNERS or frontmatter when present.
- **Research:** Does commit-age predict mentor-judged staleness better than file mtime alone?
- **Evaluate:** Precision of "needs review" flags on a labelled sample. Report only; do not auto-close pages.

### KN5. Jira duplicate hint CLI (M)

- **Recommended tech stack:** Python `httpx` read-only Jira search against project VD (Atlassian MCP or REST), TF-IDF or embedding similarity over summary/description text, CLI Markdown output. Respect `maxResults` limits from workspace conventions.
- **MVP:** Given a draft issue summary, list the top similar open or recently closed VD issues with links and similarity scores.
- **Research:** Does adding description text improve duplicate hints over summary-only matching?
- **Evaluate:** Mentor-rated relevance on held-out drafts and false duplicate rate. Read-only; never create or transition issues from the MVP.

---

## 6. Workflow analytics: deterministic charts from sanitized exports

Distinct from project 2 (claim free-text mining) and AR2 (LLM KPI narrative). Compute first; optional commentary later.

### WA1. Work-order aging snapshot (S)

- **Recommended tech stack:** Python/pandas, Plotly histograms and Jinja2 for one sanitized work order export; pytest on bucket totals.
- **MVP:** Bucket open work orders by age and status for one dealer or region snapshot, with reproducible totals.
- **Research:** Which age thresholds match BA triage habits better than equal-width bins?
- **Evaluate:** Recomputed totals vs the source export and BA usefulness. No causal claims in the MVP narrative.

### WA2. Status-transition graph (M)

- **Recommended tech stack:** Python over status-history or audit-derived transitions for NVSO or work order; NetworkX or plain adjacency matrices; Plotly sankey; JSON fixtures.
- **MVP:** Build a transition graph with counts and median time-in-status between states for one workflow.
- **Research:** Do unexpected edges reveal configuration or data-entry issues mentors already know about?
- **Evaluate:** Graph correctness on a labelled mini-trace and stability across two extracts. Document impossible transitions separately from rare ones.

### WA3. Warranty rejection Pareto (S)

- **Recommended tech stack:** Python/pandas over coded rejection reasons (not free text); Pareto chart with Plotly; Jinja2.
- **MVP:** Rank rejection reasons by volume and share for one model-year window and export the underlying counts.
- **Research:** Does a weekly Pareto change BA priority compared with a monthly rollup?
- **Evaluate:** Count fidelity and mentor confirmation that top reasons are actionable codes. Leave free-text clustering to project 2.

### WA4. Parts availability wait baseline (M)

- **Recommended tech stack:** Python/pandas joining sanitized parts request and receipt timestamps; survival-style simple Kaplan–Meier or percentile waits; Plotly; pytest on join keys.
- **MVP:** Estimate wait-time distributions from request to availability for one parts pathway.
- **Research:** How sensitive are medians to cancelled or reopened requests?
- **Evaluate:** Join accuracy and agreement with a BA spot-check sample. Label censored cases explicitly.

### WA5. Appointment no-show baseline (M)

- **Recommended tech stack:** Python/pandas, scikit-learn logistic regression versus a naive rate baseline; fixed feature set from sanitized appointment exports; Streamlit for coefficient inspection.
- **MVP:** Compare a simple model to the historical no-show rate on a held-out week for one service center extract.
- **Research:** Which features (lead time, channel, model) improve lift over the naive baseline?
- **Evaluate:** AUC or Brier score versus the naive baseline and calibration plots. Advisory analytics only; do not automate penalties or customer contact from this pilot.

---

## 7. Client and solution hygiene: forms, scripts and registrations

Distinct from project 9 (deploy pipeline) and AR3 (release evidence narrative). Prefer saved formXML, one web resource or two solution exports.

### HY1. Xrm.WebApi call inventory (S)

- **Recommended tech stack:** Node script with regex/AST over one webresource folder; CSV of `Xrm.WebApi` and remaining SOAP call sites; Markdown summary. Pair with `node --check` on touched files.
- **MVP:** Inventory retrieve/update/execute calls in one form script family with file and line references.
- **Research:** How much SOAP still remains beside async Web API in the selected area?
- **Evaluate:** Completeness against a mentor manual count on one file and zero parse crashes on minified companions when both exist. Report only; migration patches are out of scope for the MVP.

### HY2. Form onload script order map (S)

- **Recommended tech stack:** Python XML parser for one exported form; ordered list of library and event handlers; Jinja2 diagram (Mermaid or HTML).
- **MVP:** Document onload and onchange handler order for one high-traffic form with webresource names and functions.
- **Research:** Does making order visible shorten debugging of racey onload bugs?
- **Evaluate:** Match to the form XML and mentor confirmation. Diff two form versions as a stretch.

### HY3. Command bar unused-command report (M)

- **Recommended tech stack:** Python comparing ribbon/command XML to enable rules and webresource handlers; optional usage hints from a sanitized App Insights page-view export; Jinja2.
- **MVP:** List commands on one entity that lack handlers, always-hide rules or have no observed invocation in a provided usage export.
- **Research:** How often "unused" is a rare privileged action versus true dead UI?
- **Evaluate:** Precision after mentor review; keep false "delete me" suggestions low. No ribbon edits in the MVP.

### HY4. Solution-layer component summary (M)

- **Recommended tech stack:** Python over two saved solution or layer exports; component-type tallies; Jinja2 comparison. Align vocabulary with existing deploy/verify skills without invoking PAC writes.
- **MVP:** Summarize component counts and ownership layers for one unmanaged DEV solution versus a baseline export.
- **Research:** Which component types churn most between the two snapshots?
- **Evaluate:** Count agreement with Solution Packager or PAC list output on a sample and clear unknown buckets for unmapped types.

### HY5. Plugin step versus source registration checker (M)

- **Recommended tech stack:** Python or PowerShell comparing a saved plugin-step export to attributes declared in source (`CrmPluginRegistration` attributes or DevKit JSON); CSV of mismatches; pytest fixtures.
- **MVP:** For one assembly, report steps present in the environment export but missing from source declarations, and the reverse.
- **Research:** How often mismatches are intentional legacy registrations versus true drift?
- **Evaluate:** Precision on a mentor-labelled assembly and clear handling of dynamic step names. Read-only; registration fixes stay with plugin owners.

---

## Wave-2 suggested starting shortlist

Planning judgement only. Confirm module, fixtures and mentor capacity before assigning work.

| Area | First choice | Why start here | Research alternative |
| --- | --- | --- | --- |
| Data quality | DQ5: User-local date mismatch | Documented PROD fixture already exists | DQ2: VIN consistency |
| Integration reliability | IR2: Interface-log failure digest | Offline logs and a clear triage baseline | IR1: Payload contract snapshot |
| Privacy and access | PII: Dataset PII linter | Guards golden files before commit | PA2: Log field allowlist |
| Localization | LG2: Glossary drift checker | Uses tracked docs only | LG1: Untranslated label inventory |
| Knowledge navigation | KN1: Skill citation checker | Fast, read-only, high signal for this repo | KN4: Runbook freshness |
| Workflow analytics | WA1: Work-order aging snapshot | One export yields a reviewable chart | WA3: Warranty rejection Pareto |
| Client/solution hygiene | HY1: Xrm.WebApi call inventory | One folder, deterministic parse | HY2: Form onload order map |

**Optional interest pairings (discussion only):** Trần An Thắng can explore KN2 or PA5; Trần Trung Hiếu can explore WA3 or DQ1; Trần Huy Hoàng can explore IR2 or IR5; Lê Trung Hiếu can explore HY5 or PA2. These do not change the primary assignments.

For a shared wave-2 demo, connect **DQ5 → LG4 → PII**: detect a date-boundary mismatch, lock locale formatting tests, then lint the supporting dataset for PII before it is shared.
