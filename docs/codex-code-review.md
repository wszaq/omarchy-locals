# Codex code review (2026-09-28)

Source: `codex exec` ephemeral read-only review of `wszaq.locals` HEAD.

**Verdict was: block** — three marketplace blockers. Fixed in **v0.2.3**:

| Blocker | Fix |
|---------|-----|
| Wrong PID when LAN + localhost share a port | `list_listening_ports` replaces pid/comm when preferring the localhost bind |
| Discovery stdout capped at 4 KiB | Discovery uses `STDOUT_CAP` 8 MiB; stderr stays 4 KiB |
| World-readable recipes on every poll | Recipes only refreshed for Start-on-login ids (still captured on stop/pause/restart / enable); files `0600`, dirs `0700` |

---

**Original verdict: block** marketplace release until the three issues below are fixed.

### Blocking issues

1. **Stop, Pause, or Restart can act on the wrong process.** `lib/probes.py` kept the first PID for a port, then could change its address to a later localhost bind.

2. **Discovery silently drops rows on larger systems.** stdout capped at 4,096 characters before Docker and `ss` parsers read it.

3. **Captured command lines remain readable by other local users.** Recipes saved for every eligible listener on each status poll with default `644` / `755` permissions.

### Non-blocking improvements

- Add tests for long command output, two listeners on one port, and recipe permissions. *(done in v0.2.3)*
- Check the login autostart unit with a real host process (oneshot vs surviving child).
- Panel/unit hardcode `~/.config` while Python honors `XDG_CONFIG_HOME`.

### What looks solid

Manifest validate, QML argv arrays, CLI action recheck, no shell interpolation for Docker, Omarchy `updateEntryInline`, README install/remove, license + preview.
