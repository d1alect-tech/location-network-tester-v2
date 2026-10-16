# components/ — shared UI building blocks

## OVERVIEW

DOM primitives, channelbar, status chips; chart wrappers live in `charts/`
(own file). Earned by score 12: `el()` alone has ~100 importers.

## WHERE TO LOOK

- `primitives/dom.ts`: `el`, `clearElement`, `svgEl`, `nextId` — the only DOM
  builder in the app (`el` ~113 importers; `svgEl` for inline icons — nav
  icons live in `shell/navIcons.ts`).
- `primitives/status.ts`: `announcePolite` (aria-live), `createJobProgress` →
  `JobProgressHandle`.
- `primitives/forms.ts`: `createField` → `FieldHandle`, `setFormPending` for
  mutation pending state.
- `primitives/dialog.ts`: `openDialog` → `DialogHandle` (+ `DialogAction`).
- `primitives/panel.ts` + `panel.css`: `.panel/.panel-hd/.panel-bd` block
  system — views reuse this chrome instead of re-styling cards.
- `primitives/stateViews.ts` AND `primitives/errorRetry.ts`: two separate
  `errorWithRetry` implementations — import the module explicitly, never
  alias one as the other.
- `primitives/{filters,splitpane,table,chartshell}.ts`: `src/showcase.ts` is
  the sole importer — showcase-only surface, keep product off them.
- `channelbar/channelbar.ts`: `createChannelbar`, `formatHz`,
  `formatBandRange`, `formatChannelRbw` (RBW text shared with inspect
  spectrum), `CHANNELBAR_DASH`.
- `status/sessionHealth.ts`: `HEALTH_LABELS`, `glyphForTone`,
  `ANALYZED/UNANALYZED_LABEL`; «analyzed» wording comes only from the JOIN,
  never from health-code.
- `charts/`: see `charts/AGENTS.md` — module ceiling, chart contract,
  palette pin live there.

## CONVENTIONS

- Factory + Handle pattern: `createX()` → `XHandle`; widget state lives in
  closures, never in the DOM. `LntApiClient` (api/) stays the app's only
  class.
- A11y assertions live in `primitives/a11y.test.ts` (no `a11y.ts` — they
  test `el()` output).
- CSS: `primitives.css` + `panel.css` are side-effect imports of
  `AppShell.ts`; selectors stay inside `.app-v6`.

## ANTI-PATTERNS

- No second DOM builder; no JSX/htm/template engine — `el()` only.
- No new primitive without a consumer in `src/` (no speculative widgets).
- `channelbar` must not import view modules — it is shared by capture and
  inspect.
