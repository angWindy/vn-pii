"""Install PII linter hook configs into a coding agent's config dir.

Templates live under ``pii_linter/hooks/templates/`` and are read via
``importlib.resources`` so the wheel carries them. This module never
auto-runs — the user must invoke ``pii-lint install-hooks <agent>``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Literal

# Agent -> (config file path, format, merge strategy)
# "merge" for JSON means: read existing JSON, update the relevant key,
#   write back. "replace" for TOML means: append the [project] block
#   only if the file does not already have a `notify` line.
Agent = Literal["claude-code", "cursor", "cody", "codex", "aider", "all"]

_TEMPLATES = resources.files("pii_linter.hooks.templates")


@dataclass(frozen=True)
class InstallPlan:
    agent: str
    target: Path
    template_name: str
    kind: Literal["json", "toml", "bash_wrapper"]
    label: str  # human-readable for log


def _read_text(name: str) -> str:
    return (_TEMPLATES / name).read_text(encoding="utf-8")


def _read_bytes(name: str) -> bytes:
    return (_TEMPLATES / name).read_bytes()


def _home() -> Path:
    return Path(os.environ.get("HOME") or Path.home())


def _project_root() -> Path:
    """Find the current project root by walking up looking for ``.git``."""
    cwd = Path.cwd()
    for p in (cwd, *cwd.parents):
        if (p / ".git").exists():
            return p
    return cwd


def plans_for(
    agents: list[str], scope: Literal["user", "project"]
) -> list[InstallPlan]:
    """Return the list of (agent, target_path) pairs to install."""
    home = _home()
    proj = _project_root() if scope == "project" else None

    out: list[InstallPlan] = []
    for a in agents:
        if a == "claude-code":
            base = proj if scope == "project" else home
            out.append(
                InstallPlan(
                    agent=a,
                    target=base / ".claude" / "settings.json",
                    template_name="claude-code.json",
                    kind="json",
                    label="Claude Code",
                )
            )
            # PreToolUse needs a real script to do JSON parsing; ship it
            # next to settings.json so the agent can exec it by absolute
            # path. The sibling lookup in install() also patches the
            # __PII_PRETOOLUSE_PATH__ placeholder in the JSON above.
            out.append(
                InstallPlan(
                    agent=a,
                    target=base / ".claude" / "hooks" / "pii-lint-pretooluse.sh",
                    template_name="claude-pretooluse.sh",
                    kind="bash_wrapper",
                    label="Claude Code PreToolUse script",
                )
            )
        elif a == "cursor":
            base = proj if scope == "project" else home
            out.append(
                InstallPlan(
                    agent=a,
                    target=base / ".cursor" / "hooks.json",
                    template_name="cursor.json",
                    kind="json",
                    label="Cursor",
                )
            )
        elif a == "cody":
            base = proj if scope == "project" else home
            out.append(
                InstallPlan(
                    agent=a,
                    target=base / ".config" / "sourcegraph" / "cody.json",
                    template_name="cody.json",
                    kind="json",
                    label="Cody (Sourcegraph)",
                )
            )
        elif a == "codex":
            base = proj if scope == "project" else home
            out.append(
                InstallPlan(
                    agent=a,
                    target=base / ".codex" / "config.toml",
                    template_name="codex.toml",
                    kind="toml",
                    label="Codex CLI",
                )
            )
            # Codex also needs the notify script in a stable location.
            out.append(
                InstallPlan(
                    agent=a,
                    target=base / ".codex" / "hooks" / "codex-notify.sh",
                    template_name="codex-notify.sh",
                    kind="bash_wrapper",
                    label="Codex notify script",
                )
            )
        elif a == "aider":
            # Aider is a shell wrapper, not a config file. Drop it next
            # to `pii-lint` so users can `pii-lint-aider` or alias it.
            bindir = _bindir_for_pa1()
            out.append(
                InstallPlan(
                    agent=a,
                    target=bindir / "pii-lint-aider",
                    template_name="aider.sh",
                    kind="bash_wrapper",
                    label="Aider wrapper (pii-lint-aider)",
                )
            )
    return out


def _bindir_for_pa1() -> Path:
    """Return the bin dir of the running ``pii-lint`` executable."""
    exe = shutil.which("pii-lint")
    if not exe:
        return _home() / ".local" / "bin"
    return Path(exe).resolve().parent


def _strip_comment_keys(obj: dict) -> dict:
    """Remove the leading-underscore _comment key we use for documentation."""
    return {k: v for k, v in obj.items() if not k.startswith("_")}


def _merge_json(target: Path, new_payload: dict) -> dict:
    """Merge a new PII payload into an existing JSON file.

    Strategy: deep-merge by key. For each top-level key in the new
    payload:
      - dict values are merged key-by-key.
      - list values replace the existing key (safe for matcher arrays).
      - other scalars replace.

    For ``hooks`` specifically, we merge event-by-event so a pre-existing
    ``UserPromptSubmit`` survives a ``pii-lint install-hooks`` that
    adds ``PostToolUse`` / ``Stop``. Other top-level keys are preserved
    untouched.

    If the existing file is not valid JSON or not a dict, refuse and
    point the user at ``--force-replace``.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SystemExit(
                f"{target}: existing file is not valid JSON ({e}). "
                f"Fix it manually or pass --force-replace."
            )
        if not isinstance(existing, dict):
            raise SystemExit(
                f"{target}: existing JSON is not an object, refusing to merge."
            )
    else:
        existing = {}
    for k, v in new_payload.items():
        if (
            k in existing
            and isinstance(existing[k], dict)
            and isinstance(v, dict)
        ):
            merged = dict(existing[k])
            merged.update(v)
            existing[k] = merged
        else:
            existing[k] = v
    return existing


def _merge_toml(target: Path, new_text: str) -> str:
    """Append or update the [project] block in a TOML file.

    Codex config is small enough that we don't need full TOML parsing
    here. We just look for an existing `notify = ...` line and replace
    it, otherwise append the new [project] block at the end of the file.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    existing = target.read_text(encoding="utf-8") if target.exists() else ""

    # Strip leading comment lines (those starting with `#`) so the
    # user's existing config is not littered with our docs.
    new_block = re.sub(r"(?m)^#.*\n?", "", new_text).strip()

    notify_re = re.compile(r'(?m)^notify\s*=\s*\[.*\]\s*$')
    if notify_re.search(existing):
        # Replace the matched line with the first new line (the notify= line).
        new_notify_line = next(
            (ln for ln in new_block.splitlines() if ln.startswith("notify")), None
        )
        if new_notify_line is None:
            return existing
        return notify_re.sub(new_notify_line, existing)
    if existing.strip():
        return existing.rstrip() + "\n\n" + new_block + "\n"
    return new_block + "\n"


def _patch_json_command_placeholder(
    payload: dict, placeholder: str, plans: list[InstallPlan]
) -> dict:
    """Replace ``placeholder`` inside any ``command`` string with the
    absolute path of the matching sibling ``bash_wrapper`` plan.

    Claude Code nests the command under
    ``hooks.<event>[].hooks[].command`` (4 levels), so we walk the
    structure looking for the placeholder and substitute in place.
    Returns the (mutated) payload for chaining.
    """
    if placeholder not in json.dumps(payload):
        return payload
    # Find sibling by template_name matching the placeholder:
    #   __PII_PRETOOLUSE_PATH__ -> claude-pretooluse.sh
    #   __PII_NOTIFY_PATH__     -> codex-notify.sh
    target_template = {
        "__PII_PRETOOLUSE_PATH__": "claude-pretooluse.sh",
        "__PII_NOTIFY_PATH__": "codex-notify.sh",
    }.get(placeholder)
    sibling = next(
        (p for p in plans if p.template_name == target_template), None
    )
    if sibling is None:
        return payload
    replacement = str(sibling.target)

    def walk(node):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if k == "command" and isinstance(v, str) and placeholder in v:
                    node[k] = v.replace(placeholder, replacement)
                else:
                    walk(v)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return payload


def install(
    agents: list[str], scope: str, force_replace: bool = False, dry_run: bool = False
) -> int:
    """Install hook configs. Returns 0 on success, 1 on any failure.

    Logs each step to stdout in a human-readable form so users can see
    exactly which files were written.
    """
    plans = plans_for(agents, scope)  # type: ignore[arg-type]
    if not plans:
        print("No agents selected. Use one of: claude-code, cursor, cody, codex, aider, all")
        return 1

    failures = 0
    for plan in plans:
        try:
            if plan.kind == "json":
                template = json.loads(_read_text(plan.template_name))
                template = _strip_comment_keys(template)
                if force_replace and plan.target.exists():
                    merged = template
                else:
                    merged = _merge_json(plan.target, template)
                # Patch absolute path placeholders after the merge so
                # they point at sibling bash_wrapper plans. We walk
                # the merged structure (Claude Code nests the command
                # string under hooks.<event>[].hooks[].command).
                for placeholder in ("__PII_PRETOOLUSE_PATH__",):
                    merged = _patch_json_command_placeholder(
                        merged, placeholder, plans
                    )
                payload = json.dumps(merged, indent=2) + "\n"
                if dry_run:
                    print(f"[dry-run] would write {plan.target} ({plan.label})")
                    print(payload)
                else:
                    plan.target.write_text(payload, encoding="utf-8")
                    print(f"wrote {plan.target} ({plan.label})")
            elif plan.kind == "toml":
                template = _read_text(plan.template_name)
                if force_replace and plan.target.exists():
                    plan.target.unlink()
                # The codex template uses __PII_NOTIFY_PATH__ as a
                # placeholder for the on-disk path of the notify script.
                # This entry's sibling plan writes that script, so we
                # find it by looking through plans_for output.
                if "__PII_NOTIFY_PATH__" in template:
                    sibling = next(
                        (p for p in plans if p.kind == "bash_wrapper"),
                        None,
                    )
                    if sibling is not None:
                        template = template.replace(
                            "__PII_NOTIFY_PATH__", str(sibling.target)
                        )
                merged = _merge_toml(plan.target, template)
                if dry_run:
                    print(f"[dry-run] would write {plan.target} ({plan.label})")
                else:
                    plan.target.write_text(merged, encoding="utf-8")
                    print(f"wrote {plan.target} ({plan.label})")
            elif plan.kind == "bash_wrapper":
                body = _read_bytes(plan.template_name)
                if dry_run:
                    print(f"[dry-run] would write {plan.target} (mode 0755) ({plan.label})")
                else:
                    plan.target.parent.mkdir(parents=True, exist_ok=True)
                    plan.target.write_bytes(body)
                    plan.target.chmod(
                        stat.S_IRWXU
                        | stat.S_IRGRP
                        | stat.S_IXGRP
                        | stat.S_IROTH
                        | stat.S_IXOTH
                    )
                    print(f"wrote {plan.target} (mode 0755) ({plan.label})")
        except Exception as e:  # noqa: BLE001 - we want to keep going
            print(f"FAILED {plan.target}: {e}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0