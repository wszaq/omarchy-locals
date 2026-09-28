# Install

## From the marketplace / GitHub

```bash
omarchy plugin add https://github.com/wszaq/omarchy-locals.git --enable
omarchy bar move wszaq.locals --before omarchy.monitor
```

Optional defaults (Ports off is already the default):

```bash
omarchy bar set wszaq.locals showContainers true --json
omarchy bar set wszaq.locals showLocalhosts true --json
omarchy bar set wszaq.locals showPorts false --json
```

## Desktop card

In the Widgets editor (brittiiaa.widgets), enable `wszaq.locals` as a 2×2 card, or add it to `~/.config/omarchy/widgets.json`.

## Optional login autostart

```bash
~/.config/omarchy/plugins/wszaq.locals/systemd/install-autostart.sh install
```

See [Autostart](Autostart.md).

## Uninstall

```bash
~/.config/omarchy/plugins/wszaq.locals/systemd/install-autostart.sh uninstall  # if enabled
omarchy plugin disable wszaq.locals
omarchy plugin remove wszaq.locals --yes
```

User files under `~/.config/omarchy/locals/` and `~/.local/state/omarchy/locals/` are kept until you delete them.
