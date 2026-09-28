"""Autostart list + start recipes for wszaq.locals.

Autostart ids live in ~/.config/omarchy/locals/autostart.json.
Host start recipes live in ~/.local/state/omarchy/locals/recipes/<safe-id>.json
(captured from /proc/<pid>/cmdline + cwd while the process is alive).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

SCHEMA_VERSION = 1


def default_autostart_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "omarchy" / "locals" / "autostart.json"


def default_recipes_dir() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(xdg) / "omarchy" / "locals" / "recipes"


def recipe_path_for(target_id: str, recipes_dir: Path | None = None) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._:-]+", "_", str(target_id).strip()) or "unknown"
    return (recipes_dir or default_recipes_dir()) / f"{safe}.json"


def load_autostart(path: Path | None = None) -> tuple[list[str], list[str]]:
    """Return (ids, errors). Missing file → empty list."""
    p = path or default_autostart_path()
    if not p.exists():
        return [], []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [], [f"autostart read error: {exc}"]
    if not isinstance(raw, dict):
        return [], ["autostart root must be an object"]
    items = raw.get("ids", [])
    if items is None:
        items = []
    if not isinstance(items, list):
        return [], ["autostart.ids must be an array"]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        tid = str(item or "").strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        out.append(tid)
    return out, []


def save_autostart(ids: list[str], path: Path | None = None) -> tuple[bool, str]:
    p = path or default_autostart_path()
    # Stable unique order.
    seen: set[str] = set()
    clean: list[str] = []
    for tid in ids:
        t = str(tid or "").strip()
        if not t or t in seen:
            continue
        seen.add(t)
        clean.append(t)
    payload = {"schemaVersion": SCHEMA_VERSION, "ids": clean}
    try:
        p.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(p.parent, 0o700)
        except OSError:
            pass
        tmp = p.with_suffix(p.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
        os.replace(tmp, p)
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return True, str(p)
    except OSError as exc:
        return False, str(exc)


def set_autostart(target_id: str, enabled: bool, path: Path | None = None) -> tuple[bool, dict]:
    """Add or remove an id. Returns (ok, result_dict)."""
    tid = str(target_id or "").strip()
    if not tid:
        return False, {"ok": False, "error": "empty id"}
    ids, errors = load_autostart(path)
    if errors:
        return False, {"ok": False, "error": errors[0]}
    if enabled:
        if tid not in ids:
            ids.append(tid)
    else:
        ids = [x for x in ids if x != tid]
    ok, detail = save_autostart(ids, path)
    if not ok:
        return False, {"ok": False, "error": detail, "id": tid}
    return True, {
        "ok": True,
        "id": tid,
        "autostart": enabled,
        "ids": ids,
        "path": detail,
    }


def load_recipe(target_id: str, recipes_dir: Path | None = None) -> dict | None:
    path = recipe_path_for(target_id, recipes_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    argv = raw.get("argv")
    cwd = raw.get("cwd")
    if not isinstance(argv, list) or not argv or not isinstance(cwd, str) or not cwd:
        return None
    return {
        "id": str(raw.get("id") or target_id),
        "kind": str(raw.get("kind") or "port"),
        "argv": [str(a) for a in argv],
        "cwd": cwd,
        "comm": raw.get("comm"),
        "port": raw.get("port"),
        "capturedAt": raw.get("capturedAt"),
    }


def save_recipe(
    target_id: str,
    *,
    argv: list[str],
    cwd: str,
    kind: str = "port",
    comm: str | None = None,
    port: int | None = None,
    recipes_dir: Path | None = None,
) -> tuple[bool, str]:
    if not argv or not cwd:
        return False, "argv/cwd required"
    path = recipe_path_for(target_id, recipes_dir)
    payload = {
        "schemaVersion": SCHEMA_VERSION,
        "id": target_id,
        "kind": kind,
        "argv": list(argv),
        "cwd": cwd,
        "comm": comm,
        "port": port,
        "capturedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        tmp = path.with_suffix(path.suffix + ".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, indent=2) + "\n")
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return True, str(path)
    except OSError as exc:
        return False, str(exc)


def can_autostart_row(row: dict, *, has_recipe: bool) -> bool:
    """Whether Start on login is meaningful for this status row."""
    kind = row.get("kind")
    if kind == "docker":
        name = (row.get("meta") or {}).get("container") or row.get("container")
        return bool(str(name or "").strip())
    if kind == "port":
        meta = row.get("meta") or {}
        if meta.get("dockerBacked"):
            return False
        if has_recipe:
            return True
        # Live controllable process can capture a recipe now.
        return bool(meta.get("canRestart") or meta.get("pid"))
    return False


def annotate_status_rows(
    status: dict,
    *,
    autostart_ids: list[str] | None = None,
    recipes_dir: Path | None = None,
) -> dict:
    """Attach autostart / hasRecipe / canAutostart flags; enable Start when recipe exists."""
    ids = set(autostart_ids if autostart_ids is not None else load_autostart()[0])
    rows = status.get("targets") or []
    for row in rows:
        tid = str(row.get("id") or "")
        recipe = load_recipe(tid, recipes_dir) if row.get("kind") == "port" else None
        has_recipe = recipe is not None
        row["autostart"] = tid in ids
        row["hasRecipe"] = has_recipe
        row["canAutostart"] = can_autostart_row(row, has_recipe=has_recipe)
        if (
            row.get("kind") == "port"
            and row.get("state") == "stopped"
            and has_recipe
            and "start" not in (row.get("actions") or [])
        ):
            actions = list(row.get("actions") or [])
            actions.insert(0, "start")
            row["actions"] = actions
            if not row.get("primary"):
                row["primary"] = "start"
            row["statusOnly"] = False
        meta = dict(row.get("meta") or {})
        if has_recipe and recipe:
            meta["hasRecipe"] = True
            if recipe.get("comm"):
                meta.setdefault("comm", recipe["comm"])
        row["meta"] = meta

    # Keep groups in sync with mutated targets (same object refs usually, but
    # rebuild lists keyed by id to be safe).
    by_id = {r["id"]: r for r in rows}
    groups = status.get("groups") or {}
    for key in ("containers", "localhosts", "ports"):
        groups[key] = [by_id[r["id"]] if r.get("id") in by_id else r for r in (groups.get(key) or [])]
    status["groups"] = groups
    status["autostartIds"] = sorted(ids)
    status["autostartPath"] = str(default_autostart_path())
    return status
