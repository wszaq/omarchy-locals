# Autostart (after login / reboot)

1. While a service is running, open **Actions ▾** → **Start on login**.
2. Marks are stored in `~/.config/omarchy/locals/autostart.json`.
3. Host recipes (cmdline + cwd) live in `~/.local/state/omarchy/locals/recipes/`.
4. Enable the oneshot once:

```bash
~/.config/omarchy/plugins/wszaq.locals/systemd/install-autostart.sh install
```

5. Dry-run: `wszaq-locals autostart --dry-run`
6. Prefs → **Run autostart now**, or `wszaq-locals autostart`

Docker targets get `docker start` (with short retries). Localhosts need a captured recipe.
