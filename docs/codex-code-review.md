# Codex code review (2026-09-28)

Source: `codex exec` ephemeral read-only review of `wszaq.locals` HEAD.

**Verdict: block** marketplace release until the three issues below are fixed.

### Blocking issues

1. **Stop, Pause, or Restart can act on the wrong process.** [lib/probes.py](/home/thinkhub/.config/omarchy/plugins/wszaq.locals/lib/probes.py:235) keeps the first PID for a port, then can change its address to a later localhost bind. With a LAN listener on port 3000 before a localhost listener on port 3000, I reproduced a row that shows `127.0.0.1:3000` but holds the LAN process’s PID. [bin/wszaq-locals](/home/thinkhub/.config/omarchy/plugins/wszaq.locals/bin/wszaq-locals:413) signals that PID.

2. **Discovery silently drops rows on larger systems.** [lib/probes.py](/home/thinkhub/.config/omarchy/plugins/wszaq.locals/lib/probes.py:61) caps *stdout* at 4,096 characters before the Docker and `ss` parsers read it. Complete rows after that limit disappear; a cut JSON row also fails to parse. The command can still report success.

3. **Captured command lines remain readable by other local users.** [bin/wszaq-locals](/home/thinkhub/.config/omarchy/plugins/wszaq.locals/bin/wszaq-locals:215) saves recipes for every eligible listener on each status poll, including processes whose owners never select autostart. [lib/persist.py](/home/thinkhub/.config/omarchy/plugins/wszaq.locals/lib/persist.py:156) uses default file permissions. I confirmed existing recipe directories are `755` and recipe files are `644`. Arguments can contain secrets, and the files persist after the process exits.

### Non-blocking improvements

- Add tests for long command output, two listeners on one port, and recipe permissions. The current fixtures miss these cases.
- Check the login autostart unit with a real host process. [systemd/wszaq-locals-autostart.service](/home/thinkhub/.config/omarchy/plugins/wszaq.locals/systemd/wszaq-locals-autostart.service:10) is a oneshot unit; the review did not establish whether a spawned host process survives its completion.
- [Panel.qml](/home/thinkhub/.config/omarchy/plugins/wszaq.locals/Panel.qml:58) and the unit use `~/.config` paths while the Python code supports XDG config paths. A custom `XDG_CONFIG_HOME` can break those entry points.

### What looks solid

The manifest passes the installed `omarchy plugin validate` check. QML sends actions as argument arrays, the CLI checks each action against a fresh status row, and Docker commands do not use shell interpolation. Settings use Omarchy’s `updateEntryInline` path. The README includes install and removal steps, and the repo has a license and preview.

**Check limits:** The suite ran 61 tests. Six could not create temporary files in this read-only sandbox; the other 55 passed. `qmllint` exited successfully but reported unresolved Omarchy imports when run outside the shell. The live `doctor` and `status` results were limited by this sandbox’s Docker and netlink access.
