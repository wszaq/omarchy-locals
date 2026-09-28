# AGENTS.md — wszaq.locals

## First commands

```sh
./bin/wszaq-locals doctor
./bin/wszaq-locals status --json
```

Config (optional) at `~/.config/omarchy/locals/targets.json`.
Runtime logs: `~/.local/state/omarchy/locals/log.jsonl`.

Missing or empty config is the plug-and-play path: auto-discover Docker
containers + localhost listeners every poll. Pins/ignore only refine that.

## Where to change what

| Symptom | Likely file |
|---------|-------------|
| Wrong state/actions / merge / ignore / classify / sort / bar counts | `lib/model.py` + fixture in `tests/` |
| Probe / docker ps / ss discovery | `lib/probes.py` + fixture fake `run` |
| CLI verbs / ignore append / doctor / filter flags | `bin/wszaq-locals` |
| Bar glyph, sections, icon toolbar, sort, Prefs, empty copy | `Panel.qml` |
| Schema defaults (`showPorts`, `sortMode`, …) | `manifest.json` + `omarchy bar set` |

A behavior change often needs model + CLI together. Change QML when displayed
state or controls are wrong. Do not chase live containers for tests — add a
fixture probe result instead.

## Validate

```sh
python3 -m unittest discover -s tests -v
/usr/lib/qt6/bin/qmllint Panel.qml || true
omarchy plugin validate .
./bin/wszaq-locals doctor
./bin/wszaq-locals status --json
```

Card surface: brittiiaa.widgets embeds this Panel by lifting `KeyboardPanel`
content (same path as omascribe.control). After QML layout changes, enable a
2×2 card in `~/.config/omarchy/widgets.json` or via the Widgets editor and
confirm controls are not clipped.

## Trust boundary

This plugin runs unsandboxed inside `omarchy-shell`. QML may only spawn
`bin/wszaq-locals` via `Quickshell.Io.Process` argument arrays. The CLI looks
up the target id and rechecks allowed actions.

**Docker** rows: start/stop/pause/resume/restart via `docker`.
**Host listeners** with a known same-user PID (not `docker-proxy`, not
denylisted system daemons): stop (SIGTERM→SIGKILL), pause (SIGSTOP),
resume/wake (SIGCONT), restart (re-exec `/proc/<pid>/cmdline` + cwd when
readable). Denylisted names stay Open/Ignore only.

## Out of scope (deferred)

Compose projects, systemd user units, docker events stream (poll is enough),
Start for discovered-only processes after Stop (no cmdline left to re-exec).
