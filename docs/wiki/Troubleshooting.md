# Troubleshooting

## Doctor

```bash
~/.config/omarchy/plugins/wszaq.locals/bin/wszaq-locals doctor
~/.config/omarchy/plugins/wszaq.locals/bin/wszaq-locals status --json
```

## Docker unavailable

The Containers section notes when the daemon is down. Localhosts/Ports still work. Start Docker, then refresh (poll or reopen the panel).

## No Stop on a row

System daemons and `docker-proxy` ports are Open/Ignore only. User apps with a readable PID get Stop/Pause. Containers need a running Docker daemon.

## Panel did not update

```bash
omarchy-shell shell rescanPlugins
# or
omarchy restart shell
```

## Validate

```bash
omarchy plugin validate ~/.config/omarchy/plugins/wszaq.locals
python3 -m unittest discover -s ~/.config/omarchy/plugins/wszaq.locals/tests -v
```
