# Configuration

Config is **optional**. With no file, discovery still runs.

Path: `~/.config/omarchy/locals/targets.json`

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
| `ignore` | Hide discovery noise (`name`, `docker:name`, `53`, `port:53`) |
| `targets` | Pins: labels/URLs; docker pins are not duplicated |

Bar-widget settings (in `shell.json` / Prefs): `showContainers`, `showLocalhosts`, `showPorts`, `sortMode`, `pollIntervalSec`.
