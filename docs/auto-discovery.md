# Auto-discovery (v1.2)

wszaq.locals no longer requires `targets.json` to show anything useful.

## Each poll

1. **Docker** — if the daemon answers `docker info`, run
   `docker ps -a --format '{{json .}}'` and emit a row per container
   (`id` = `docker:<name>`, `group` = `container`). States map to running /
   paused / stopped / unknown. Controls: start, stop, pause, resume, restart.
   Absent daemon → Containers section explains unreachable.

2. **Localhost ports** — parse `ss -ltnp`. Keep binds on loopback
   (`127.0.0.1`, `::1`) or wildcard (`0.0.0.0`, `*`, `::`). Skip LAN-only
   binds. Skip `docker-proxy` (container publish is owned by the Docker
   row). Emit `port:<n>` status-only rows, then classify:

   - **Localhosts** — pinned ports; HTTP-openable ports; common app ports
     (`3000–3999`, `8000–8999`, `5173`, `8080`, `11434`, …); or process
     names like `node` / `vite` / `python` / `ollama`.
   - **Ports** — everything else (cups, mosquitto, random agents, …).

## Kind filters

Bar-widget settings `showContainers` / `showLocalhosts` / `showPorts`
(default Ports **off**) control which groups list and which rows count in
the bar digit. Status JSON echoes `filters` and exposes `groups`.

## Config (optional)

```json
{
  "ignore": ["sidecar", "port:53"],
  "targets": [ /* pins with label/url overrides */ ]
}
```

- `ignore` hides auto rows only (pins still show). Row overflow **Ignore**
  appends here.
- Pinning a docker container or port prevents a second discovered row.
- Empty / missing file ⇒ discover everything eligible.

## Bar digit

`counts.running` = running docker containers + up non-`docker-proxy`
Localhosts/Ports rows, **only for kinds switched on**. Digit display
unchanged: 0 → glyph alone, 1–9 as digit, ≥10 → `9`.

## Debug

`wszaq-locals doctor` and `status --json` remain the debug surface.
