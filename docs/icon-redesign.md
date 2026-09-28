# wszaq.locals bar icon redesign

## What was wrong

The bar used Nerd Font `󰡰` (md-docker, U+F0870) plus `running/total`. On the live top bar it sat immediately left of `omarchy.monitor`’s plain monitor glyph. Same weight, same color (`bar.foreground`), same size, and a near-identical monitor silhouette — so locals read as “another monitor/docker icon” instead of its own control.

Evidence: `docs/bar-before.png` (right-side crop of the real top bar, 2026-09-28).

## Codex recommendation (L experiment) — SUPERSEDED

From `codex exec` with `-i` on that screenshot (transcript: `docs/codex-icon-redesign.txt`):

1. **Identify:** locals = monitor+folder glyph immediately before `0/0`; plain monitor after `0/0` = `omarchy.monitor`.
2. **Why it blends:** shared monitor shape, size, weight, and color with neighbors.
3. **Redesign:** replace the normal glyph with Latin capital **`L`** (U+004C). Keep warning `󰀦` on error. Set `BarIconButton.foreground` to `root.hasError ? Color.urgent : Color.bar.text`.
4. **Rationale:** `L 0/0` is a clear shape beside the monitor icon; theme tokens keep the label readable and mark errors.

### What we applied (L experiment)

In `Panel.qml`:

- `barText()` normal glyph: `󰡰` → `L` (error glyph unchanged: `󰀦`).
- `BarIconButton.foreground: root.hasError ? Color.urgent : Color.bar.text`.

No panel/card/layout/target/control changes.

### What we rejected (L experiment)

Nothing from Codex’s proposal at the time. It used only `Color.urgent` / `Color.bar.text` (no hardcoded hex, no permanent colored pill).

**Status:** Superseded 2026-09-28. User rejected the capital-L monogram and preferred the previous Docker glyph. Codex was skipped for the rework at the user’s request.

## Rework 2026-09-28 — restore Docker glyph + single digit

### Requirements

1. Restore Nerd Font Docker glyph **U+F308** (``) — the character before the L change. Remove Latin `L`.
2. One digit only: running count. `0` → icon alone; `1`–`9` → that digit; `≥10` → `"9"`. Keep error glyph `󰀦`.
3. Match spacing to a real neighbor.

### Spacing reference: `omascribe.control`

Read `~/.config/omarchy/plugins/omascribe.control/Panel.qml`:

- `barText()` uses glyph alone, or `glyph + " " + suffix` when recording (single ASCII space gap).
- `BarIconButton` uses **defaults only**: no `slotSize` / `fontSize` / `horizontalMargin` overrides → `Style.bar.iconSlot` (27), `Style.bar.iconFont` (13), `Style.bar.iconCanvas` (16).

Locals matches that: default `BarIconButton` metrics; gap between glyph and digit is one ASCII space (only when `running > 0`).

### Applied

```qml
function barText() {
  var glyph = hasError ? "󰀦" : ""  // U+F308
  if (running <= 0)
    return glyph
  return glyph + " " + Math.min(running, 9)
}
```

Kept `foreground: root.hasError ? Color.urgent : Color.bar.text` (theme tokens). No panel/card/control/target changes.

Evidence: `docs/bar-before-rework.png` / `docs/bar-after-rework.png`.
