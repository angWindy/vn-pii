# Coding-agent hooks for PA1 PII Linter

PA1 can guard any coding agent that **exposes a hook mechanism**. Each
file in this directory is a drop-in config (or wrapper script) for one
agent. Pick the one that matches yours.

| Agent | File | Hook event | What it does |
|---|---|---|---|
| **Claude Code** | `claude-code.json` | `PostToolUse` (Write/Edit/MultiEdit) + `Stop` | Scan file after edit; run staged scan at end-of-turn |
| **Cursor** | `cursor.json` | `postToolUse` (Write/Edit/MultiEdit) + `stop` | Same shape as Claude Code |
| **Cody (Sourcegraph)** | `cody.json` | `postMessage` (edit/insert) | Scan file after Cody writes |
| **Codex CLI** | `codex.toml` + `codex-notify.sh` | `notify` | Scan staged diff at end-of-turn |
| **Aider** | `aider.sh` | (no native hooks) | Bash wrapper around `pa1-lint guard -- aider` |

## Install in 30 seconds

### Claude Code

```bash
# Merge into your user-wide settings (preserves your other hooks):
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude' / 'settings.json'
p.parent.mkdir(parents=True, exist_ok=True)
base = json.loads(p.read_text()) if p.exists() else {}
new  = json.loads(pathlib.Path('examples/hooks/claude-code.json').read_text())
base.setdefault('hooks', {}).update(new['hooks'])
p.write_text(json.dumps(base, indent=2))
"
```

Or for a single project, copy to `.claude/settings.json` and keep only the
`hooks` map.

### Cursor

```bash
mkdir -p ~/.cursor
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.cursor' / 'hooks.json'
new = json.loads(pathlib.Path('examples/hooks/cursor.json').read_text())
p.write_text(json.dumps(new, indent=2))
"
```

### Cody

```bash
mkdir -p ~/.config/sourcegraph
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.config' / 'sourcegraph' / 'cody.json'
new = json.loads(pathlib.Path('examples/hooks/cody.json').read_text())
p.write_text(json.dumps(new, indent=2))
"
```

### Codex CLI

```toml
# Append to ~/.codex/config.toml:
[project]
notify = ["bash", "/absolute/path/to/vn-pii/examples/hooks/codex-notify.sh"]
```

### Aider

```bash
# Either run directly:
./examples/hooks/aider.sh --message "refactor parser"

# Or alias it:
echo "alias aider-safe='$(pwd)/examples/hooks/aider.sh'" >> ~/.bashrc
```

## How the hooks block PII

Every hook calls `pa1-lint scan` and bubbles up its exit code:

- `0` — clean, agent continues
- `1` — HIGH (PHONE, ID_NUMBER, ACCOUNT_NO, PERSON). Hook treats this as a block.
- `2` — CRITICAL (CARD_NO) **or** the hook itself failed. Block.

The agent sees a non-zero exit, surfaces the report to the user/model,
and re-prompts itself to redact before continuing. For staged-diff hooks
(`Stop`, `stop`, `notify`), the working tree must be clean before the
agent signs off.

## Caveats

- **PostToolUse sees only the file you just touched.** Other PII that
  already exists in the working tree is not scanned unless you also wire
  a `Stop` / `stop` hook (we do, in `claude-code.json` and `cursor.json`).
- **Aider stdout is not scanned.** The wrapper scans `git diff HEAD`
  before and after the run, but anything Aider prints to its terminal
  is not captured. This is by design — see
  [`docs/user-guide.md §Wrap an AI agent`](../user-guide.md).
- **`examples/hooks/codex-notify.sh` must be `chmod +x`'d** (the others
  are config files).
- **Hook ordering**: if you already have hooks, merge rather than
  replace — PA1 adds new entries; it doesn't own the whole file.