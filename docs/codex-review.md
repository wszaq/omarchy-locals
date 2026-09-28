# Codex review — wszaq.locals

Source: `codex exec --ephemeral --sandbox read-only` (gpt-6-sol / configured model), 2026-09-28.
Invocation succeeded; this file is the recoverable review.

## Verdict

**ship-with-changes.** The core (named local targets + docker control from the bar) is useful, but the original plan granted control over processes the plugin does not own, and assumed a popup Panel would render as a wallpaper card without a host layout contract. Fix ownership and host embed before shipping.

## Blocking issues (Codex)

1. **`ss` does not grant control.** Never SIGSTOP/TERM/KILL a discovered listener. Status-only until the plugin started and re-verifies the pid. Never signal `docker-proxy`.
2. **Four kinds are too many for v1.** Defer process control, Compose, and systemd. Keep configured Docker containers + named status-only ports.
3. **Card needs an explicit presentation mode** relative to `KeyboardPanel` popup geometry.
4. **Firm config/command boundary:** `targets.json` outside the plugin checkout; poll setting inline on the bar entry; QML launches only the fixed CLI via `Process` arg arrays; CLI looks up target id and rechecks allowed actions.
5. **Status/action races:** bounded probes, discard stale responses, disable row while action runs, refresh after action; failed action leaves prior state + error; docker down marks docker rows unknown without breaking ports.
6. **AGENTS.md too rigid:** allow CLI + model + QML changes together when UI state/controls are wrong; verify both bar and card surfaces.

## Layout spec (Codex)

- **Bar:** theme glyph + `running/total` (e.g. `● 2/5`). Dim when none running. Error mark when any unknown / probe failure. Tooltip with running/paused/docker-unavailable.
- **Popup:** ~360×420, scroll list. Header “Local services” + count + refresh. Sections **Ports** / **Docker** when configured. Footer: last probe + one error. Empty → config path. Docker down → keep port rows, docker section error only.
- **Row:** label + chip; meta (port/container); primary action (Start/Pause/Resume); Stop when offered; overflow for Restart / Docker TUI / Open URL when applicable. Visibility from CLI `actions`.
- **2×2 card:** same content, no bar button / no floating popup chrome when embedded.
- **Input:** Tab through controls; Esc closes menu/popup (card stays open); busy on active row.

## What we applied

| Recommendation | How |
|---|---|
| No signals on discovered listeners | v1 `port` kind is status-only; no process start/stop/pause |
| Reduce kinds | v1 supports `docker` + `port` only; others deferred |
| Config outside plugin | `~/.config/omarchy/locals/targets.json`; state under `~/.local/state/omarchy/locals/` |
| Process arg arrays + CLI recheck | `Panel.qml` uses `Process` arrays; CLI validates action against model |
| Action race handling | Busy id in QML; status not mutated by action JSON; refresh after action |
| Docker down ≠ panel death | Port probes independent; docker unreachable → docker rows `unknown` |
| Layout structure | Glyph + count, Ports/Docker sections, row primary+Stop+overflow, empty/docker-down footers |
| AGENTS.md softer | doctor → status → fixture test; QML when UI wrong; validate both surfaces |
| Bar near `omarchy.monitor` | Enable + `omarchy bar move` after install |

## What we rejected

| Recommendation | Reason |
|---|---|
| Invent a plugin-owned `cardMode` that brittiiaa must set | Verified host already embeds `qs.Ui.Panel` by opening it and lifting `KeyboardPanel` content into the card (`WidgetInstance.embedPanel`). Custom cardMode would be unused and contradict the host contract. |
| Require brittiiaa host changes before claiming cards | Same embed path already used by `omascribe.control` / other Panel plugins; we follow that pattern. |
| Drop Docker TUI / Open URL from overflow | Codex listed them as keep in non-blocking notes; retained when applicable. |
| Symlink `~/.config/omarchy/plugins/wszaq.locals` → Work repo | `omarchy plugin validate` rejects symlinks inside a plugin folder; checkout lives in plugins, Work path is the convenience symlink the other way. |

## Adjusted v1 scope

**Keep:** docker containers (start/stop/restart/pause/unpause), named status-only ports, status/action CLI, doctor, one Panel.qml, poll interval setting.

**Defer:** process start/signals, Compose projects, systemd user units, any action on `ss`-found listeners.
