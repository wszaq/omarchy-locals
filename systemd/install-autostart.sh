#!/usr/bin/env bash
# Install (or remove) the user oneshot that runs `wszaq-locals autostart` at login.
set -euo pipefail
UNIT_SRC="$(cd "$(dirname "$0")" && pwd)/wszaq-locals-autostart.service"
UNIT_DST="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/wszaq-locals-autostart.service"

usage() {
  echo "Usage: $0 install|uninstall|status" >&2
  exit 2
}

cmd="${1:-}"
case "$cmd" in
  install)
    mkdir -p "$(dirname "$UNIT_DST")"
    install -m 644 "$UNIT_SRC" "$UNIT_DST"
    systemctl --user daemon-reload
    systemctl --user enable --now wszaq-locals-autostart.service
    systemctl --user --no-pager status wszaq-locals-autostart.service || true
    echo "Installed. Disable with: $0 uninstall"
    ;;
  uninstall)
    systemctl --user disable --now wszaq-locals-autostart.service 2>/dev/null || true
    rm -f "$UNIT_DST"
    systemctl --user daemon-reload
    echo "Removed."
    ;;
  status)
    systemctl --user --no-pager status wszaq-locals-autostart.service || true
    ;;
  *) usage ;;
esac
