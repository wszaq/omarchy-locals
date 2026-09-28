# wszaq.locals

Omarchy **bar-widget** that auto-discovers Docker containers and localhost
listeners, groups them into **Containers / Localhosts / Ports**, and lets you
toggle which kinds appear. One QML panel serves the bar popup and
brittiiaa.widgets desktop cards.

Design notes from Codex: [`docs/codex-review.md`](docs/codex-review.md).
Auto-discovery: [`docs/auto-discovery.md`](docs/auto-discovery.md).

## Install

```bash
omarchy plugin add https://github.com/wszaq/omarchy-locals.git --enable
omarchy bar move wszaq.locals --before omarchy.monitor
```

Defaults: Containers and Localhosts on, Ports off. Optional overrides:

```bash
omarchy bar set wszaq.locals showPorts false --json
```

Config is **optional** (plug-and-play). Create it only to pin labels/URLs or
hide noise:

```bash
mkdir -p ~/.config/omarchy/locals
cp ~/.config/omarchy/plugins/wszaq.locals/targets.example.json \
  ~/.config/omarchy/locals/targets.json
```

Desktop card (optional): Widgets editor, or add a `wszaq.locals` entry to
`~/.config/omarchy/widgets.json` with `"type": "wszaq.locals"`, `"cols": 2`,
`"rows": 2`, `"enabled": true`.

## Disable / uninstall

```bash
# optional: stop login autostart
~/.config/omarchy/plugins/wszaq.locals/systemd/install-autostart.sh uninstall

omarchy plugin disable wszaq.locals
omarchy plugin remove wszaq.locals --yes
```

User config under `~/.config/omarchy/locals/` and state under
`~/.local/state/omarchy/locals/` are left in place; remove those directories
manually if you want a clean slate.

## Groups

| Section | What it is |
|---------|------------|
| **Containers** | Docker containers only (`docker` kind). |
| **Localhosts** | Useful “my apps”: pinned ports; HTTP-openable listeners; common app ports (`3000–3999`, `8000–8999`, `5173`, `8080`, `11434`, …); or process names like `node` / `vite` / `python` / `ollama`. |
| **Ports** | Everything else discovered (cups, mosquitto, random agents, …). `docker-proxy` stays under Containers (never duplicated here). |

Sort: Containers default = running → paused → stopped, then A–Z. Localhosts
default = up first, then port ascending. Ports default = port ascending.
Cycle **Default / A–Z / Port** in the header (persisted as `sortMode`).

## Kind toggles (defaults)

Header filter chips (●/○) and Preferences share one source of truth — bar-widget
settings in `shell.json`:

| Key | Default | Role |
|-----|---------|------|
| `showContainers` | **on** | List + count containers |
| `showLocalhosts` | **on** | List + count local app servers |
| `showPorts` | **off** | List + count other listeners (noisy) |
| `sortMode` | `default` | `default` \| `az` \| `port` |

Persisted via `root.settings` → `bar.shell.updateEntryInline` (same path as
`omarchy.power`). Also editable in Omarchy’s widget settings UI / `omarchy bar set`.

Off kinds are hidden (no empty section). On + empty → one muted line when
other sections still have rows.

## Row controls

Each row has an **Actions ▾** menu (not a pile of on-row buttons). Entries come
from the CLI `actions` array plus Open / Ignore / Start on login when legal.

| Row type | Actions menu (when legal) |
|----------|---------------------------|
| Docker running | Pause, Stop, Restart, Start on login, Docker TUI, Ignore |
| Docker paused | Resume (wake), Stop, Restart, … |
| Docker stopped | Start, Restart, Start on login, … |
| Localhost / Port (user PID) | Pause, Stop, Restart (if cmdline readable), Open, Start on login, Ignore |
| Localhost stopped + recipe | Start, Start on login, … |
| System / docker-proxy | Open, Ignore only (never signaled) |

Ignore hides a discovered row from the list.

## Start on login (restore after reboot)

1. Open a row’s **Actions ▾** → **Start on login** (requires docker name or a
   captured host recipe — recipes are saved while the process is running).
2. Marks live in `~/.config/omarchy/locals/autostart.json`.
3. Host cmdline/cwd recipes: `~/.local/state/omarchy/locals/recipes/<id>.json`.
4. Enable the login oneshot once:

```bash
~/.config/omarchy/plugins/wszaq.locals/systemd/install-autostart.sh install
# reverse: …/install-autostart.sh uninstall
```

5. Dry-run: `wszaq-locals autostart --dry-run`
6. Prefs → **Run autostart now** (or `wszaq-locals autostart`).

Docker marked targets get `docker start` (with short retries). Localhosts need a
recipe; without one, Start on login stays disabled.

## Preferences

Open **Prefs** in the panel header. Same page covers:

1. Kind toggles (Containers / Localhosts / Ports) — identical settings as chips
2. Sort mode (Default / A–Z / Port)
3. Poll interval (seconds)
4. **Run autostart now**
5. Open `targets.json`, open config folder, Open Docker TUI

Row **Ignore** appends `docker:<name>` or `port:N` to
`~/.config/omarchy/locals/targets.json` (creates the file if needed).

## Zero config

With no `targets.json` (or `"targets": []`):

1. Each poll runs `docker ps -a` (when the daemon is up) and lists every
   container with start/stop/pause/resume/restart.
2. Each poll runs `ss -ltnp` and lists **localhost-reachable** listeners
   (binds on `127.0.0.1`, `::1`, or wildcard `0.0.0.0` / `*`). Status only —
   never signals those processes. `docker-proxy` publishes are omitted (the
   container row owns them). Classified into Localhosts vs Ports as above.
3. Docker down → Containers note; Localhosts/Ports still appear when present.
4. Ports kind starts **off**, so plug-and-play stays quiet.

## CLI

```bash
wszaq-locals doctor
wszaq-locals status --json
wszaq-locals status --json --show-ports 1
wszaq-locals status --json --sort-mode az
wszaq-locals ignore <id>
wszaq-locals start|stop|pause|resume|restart <id>
```

Discovered docker ids look like `docker:<name>`; discovered ports like
`port:3000`. Filter flags default to Containers/Localhosts on, Ports off
(matching the bar).

## Config schema

```json
{
  "ignore": ["noisy-container", "port:53", "631"],
  "targets": [
    { "id": "pg", "kind": "docker", "label": "Postgres", "container": "postgres" },
    { "id": "app", "kind": "port", "label": "App", "port": 3000, "url": "http://127.0.0.1:3000" }
  ]
}
```

| Key | Role |
|-----|------|
| `ignore` | Hide auto-discovered noise. Forms: `name`, `docker:name`, `53`, `port:53`. |
| `targets` | Optional **pins**: custom id/label/url; docker pins are not duplicated from discovery. Pinned ports always land in Localhosts. |

| kind | Controllable? | Notes |
|------|---------------|-------|
| `docker` | Yes — start/stop/restart/pause/unpause | Auto + pins → Containers |
| `port` / localhost | Stop/Pause/Resume (+ Restart when cmdline readable); Open; Ignore | Auto + pins. Never signal `docker-proxy` or denylisted system daemons. |

Deferred: `process`, `compose`, `systemd`.

## Bar digit

`counts.running` (bar digit, same 0→glyph / 1–9 / ≥10→9 rules) counts only
kinds that are **switched on**, for non-ignored rows:

- running **Docker** containers, plus
- **up** Localhosts/Ports rows that are **not** `docker-proxy` duplicates.

Paused/unknown counts are docker-oriented; port rows are up/down only.

## Trust

Runs unsandboxed inside omarchy-shell. QML only launches this CLI with
argument arrays. Docker down leaves localhost port rows working.

## Dependencies

- Omarchy shell (Quickshell)
- Python 3 (stdlib only)
- `ss` (iproute2) for port discovery
- Docker CLI optional (containers section; daemon may be down)

No install hooks and no sudo from the plugin itself. The optional login
autostart unit is installed only when you run `systemd/install-autostart.sh`.

## Development

```bash
python3 -m unittest discover -s tests -v
omarchy plugin validate .
./bin/wszaq-locals doctor
./bin/wszaq-locals status --json
```

## License

MIT.
