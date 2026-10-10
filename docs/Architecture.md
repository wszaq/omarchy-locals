# Contributor architecture

At this review, [GitHub](https://github.com/wszaq/omarchy-locals) did not mark this repository as a fork.

The [existing wiki](wiki/Home.md) covers installation and daily use. This page explains where contributors change behavior.

## Data flow

`Panel.qml` calls the Python CLI. The CLI collects probes, builds rows, and returns status data.
The manifest selects `Panel.qml` as the bar entry point. See [manifest.json](https://github.com/wszaq/omarchy-locals/blob/cdc2db622451d1bc11e201f4d76f6e420bce745d/manifest.json#L10-L28).

| File | Responsibility |
| --- | --- |
| `bin/wszaq-locals` | CLI parsing, status collection, action checks, and action logs |
| `lib/probes.py` | Docker calls, listener discovery, host signals, and resource samples |
| `lib/model.py` | Target merge, group selection, sorting, filters, and allowed actions |
| `lib/persist.py` | Saved host recipes and login marks |
| `Panel.qml` | Popup, desktop card, preferences, and action menus |

The CLI merges pins with discovered containers and eligible listeners. See [bin/wszaq-locals](https://github.com/wszaq/omarchy-locals/blob/cdc2db622451d1bc11e201f4d76f6e420bce745d/bin/wszaq-locals#L96-L140).
Model functions keep display rules separate from probes. See [lib/model.py](https://github.com/wszaq/omarchy-locals/blob/cdc2db622451d1bc11e201f4d76f6e420bce745d/lib/model.py#L825-L880).

## Actions have a second check

The CLI recollects status before an action. It rejects unknown targets and actions outside the row's allowed set.
Docker operations use the container name. Host operations check the process metadata before a signal.
A saved recipe can start a stopped host listener. See [bin/wszaq-locals](https://github.com/wszaq/omarchy-locals/blob/cdc2db622451d1bc11e201f4d76f6e420bce745d/bin/wszaq-locals#L320-L414).

Stop first sends `SIGTERM`. After three seconds, the probe can send `SIGKILL`.
Pause uses `SIGSTOP`. Resume uses `SIGCONT`. Restart needs readable command arguments and a working directory.
See [lib/probes.py](https://github.com/wszaq/omarchy-locals/blob/cdc2db622451d1bc11e201f4d76f6e420bce745d/lib/probes.py#L383-L445).

The older [auto-discovery note](auto-discovery.md) describes listener rows as status-only.
Use the current action code and [troubleshooting page](wiki/Troubleshooting.md) for the available host controls.

## Verify a change

From a working checkout, run:

```sh
python3 -m unittest discover -s tests -v
omarchy plugin validate .
```

These checks come from [AGENTS.md](https://github.com/wszaq/omarchy-locals/blob/cdc2db622451d1bc11e201f4d76f6e420bce745d/AGENTS.md#L30-L38). This documentation review did not execute them.
Use fixture probes for behavior changes. Do not depend on live containers for repeatable tests.
See [AGENTS.md](https://github.com/wszaq/omarchy-locals/blob/cdc2db622451d1bc11e201f4d76f6e420bce745d/AGENTS.md#L16-L28).
