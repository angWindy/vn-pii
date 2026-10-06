### PII. Dataset PII linter (S)

- **Recommended tech stack:** Python CLI, regex and column-name heuristics, optional `presidio-analyzer` if approved for the workstation; pytest fixtures with planted PII; exit codes for pre-commit or CI. Scan only paths the intern owns (golden JSONL, sample CSV).
- **MVP:** Flag likely names, phones, emails, national IDs and free-text blobs in one proposed golden dataset before it is committed, with a suppressions file for known synthetic fields.
- **Research:** Do column heuristics plus regex beat regex-alone on mentor-labelled columns?
- **Evaluate:** Precision/recall on planted PII, false alarms on synthetic IDs and time to clean a failing file. Never print full secret values in the report.

### See also

- [side.md](side.md) — full research notes (English)
- [side.vi.md](side.vi.md) — full research notes (Vietnamese)