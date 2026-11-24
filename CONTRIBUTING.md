# Contributing

Thank you for your interest in wszaq.locals.

## Before you start

Read [AGENTS.md](AGENTS.md). It lists where each behavior lives in the code.
Read [docs/Architecture.md](docs/Architecture.md) for the data flow.

## Report a bug

1. Open an issue in this repository on GitHub.
2. Give the Omarchy version and your operating system.
3. Give the steps to reproduce the bug.
4. Attach the output of `./bin/wszaq-locals doctor`.
5. Attach the output of `./bin/wszaq-locals status --json`.

Remove any private host names, IP addresses or tokens from the output first.

For a security issue, do not open a public issue. Follow [SECURITY.md](SECURITY.md).

## Propose a change

1. Open an issue first for a large change. Describe the problem and the proposed fix.
2. Fork the repository. Create a branch for your change.
3. Change only what your fix needs.
4. Add or update a test in `tests/`. Use fixture data, not live containers.
5. Run the checks in the next section.
6. Open a pull request. Describe what changed and how you checked it.

If the change alters what the panel shows, add a screenshot to the pull request.

## Run the checks

Run these commands from the repo root:

```bash
python3 -m unittest discover -s tests -v
omarchy plugin validate .
./bin/wszaq-locals doctor
./bin/wszaq-locals status --json
```

If the Qt 6 tools are installed, also run:

```bash
/usr/lib/qt6/bin/qmllint Panel.qml
```

After a QML layout change, enable a 2×2 desktop card. Confirm that no control is clipped.

## Style

- Use the style that the code already has.
- Keep changes small. Do not reformat code near your change.
- Write documentation in short, plain sentences.
- Do not commit secrets, tokens or private host names.
