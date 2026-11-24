# Security policy

## Report a vulnerability

Report a vulnerability in private. Do not open a public issue or a public pull request.

1. Open the **Security** tab of this repository on GitHub.
2. Select **Report a vulnerability**. This opens a private GitHub Security Advisory.
3. Describe the problem. Give the steps to reproduce it.
4. Give the plugin version from `manifest.json`.

## What to expect

The maintainer reviews the report in the private advisory. The maintainer answers in the same advisory.

## Scope

This plugin runs without a sandbox, inside omarchy-shell. It starts `bin/wszaq-locals` with argument arrays only. It never signals `docker-proxy` or denylisted system daemons. The OS refuses signals to processes of other users.

A report about any of these points is in scope. Examples are a way to start an unlisted command, or a way to signal a process that the CLI should not signal.
