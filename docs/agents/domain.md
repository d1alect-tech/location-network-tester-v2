# Domain Docs

How the engineering skills should consume this repo's domain documentation when
exploring the codebase.

## Before exploring, read these

- **`AGENTS.md`** at the repo root: the condensed knowledge base (structure, conventions,
  anti-patterns, commands, and the v1/v2 analysis boundary).
- **`README.md`**: the measurement protocol, channel modes, session format, exit codes.
  Partly lost to disk damage; the surviving text is still the authority on session layout.
- **`docs/adr/`**: read the ADRs that touch the area you're about to work in.
- **`DESIGN.md`**: design tokens, for anything touching the frontend.

There is **no `CONTEXT.md` and no `CONTEXT-MAP.md`** in this repo today. That's expected,
not a defect. If a skill asks for them, proceed silently; don't flag their absence and
don't suggest creating them upfront. `/domain-modeling` creates them lazily, if and when
terms or decisions actually get resolved.

This is a single-context repo: one Python package (`src/lnt`) plus one frontend
(`frontend/src`). There are no context-scoped `src/<context>/docs/adr/` directories, so
`docs/adr/` holds every architectural decision.

## The ADRs

All nine live in `docs/adr/`:

| ADR | Subject |
|---|---|
| ADR-0001 | canonical raw sessions |
| ADR-0002 | context.json schema 1 |
| ADR-0003 | append-only context events |
| ADR-0004 | versioned analysis artifacts |
| ADR-0005 | root legacy analysis projections |
| ADR-0006 | experiments outside sessions |
| ADR-0007 | identifiers, time and units |
| ADR-0008 | error taxonomy |
| ADR-0009 | v6 showcase final UI direction |

## File structure

```
/
├── AGENTS.md
├── README.md
├── DESIGN.md
├── docs/
│   ├── adr/                    ← the 9 ADRs above
│   ├── roadmap.md              ← the delivery queue
│   ├── operator-guide.md
│   ├── scientific-manual.md
│   ├── defect-ledger.md
│   ├── safety-and-recovery.md
│   ├── pristine-enforcement.md
│   ├── private-use-policy.md
│   └── packaging-notices.md
├── src/lnt/
├── frontend/src/
├── tests/
└── scripts/
```

`src/lnt/` subpackages, which is where the domain vocabulary actually lives:

`analysis_store`, `analysis_v2`, `apd`, `archive`, `burst`, `catalog`, `cm_dm`,
`comparability`, `config`, `context`, `events`, `experiments`, `features`, `harmonics`,
`limits`, `notching`, `power_quality`, `profiles`, `psd`, `reporting`, `research`,
`runtime`, `spectrogram`, `statistics`, `trends`, `ui`, `uncertainty`

Top-level modules carry the measurement domain directly: `acquire.py`, `manifest.py`,
`analysis.py` (v1 facade) and `analysis_v2/engine*.py`, `line_quality.py`, `needles.py`,
`spectrum.py`, `input_reference.py`, `compare.py`, `units.py`, `errors.py`.

`frontend/src/` splits into `api`, `capture`, `components`, `shell`, `state`, `views`,
`testkit`, `test-support`, plus the two showcase trees (`showcase-redesign`,
`showcase-round2` — the latter is frozen, never edit it). Views are `catalog`,
`experiments`, `inspect`, `reports`, `settings`.

`tests/` mirrors those areas: `analysis`, `archive`, `catalog`, `experiments`,
`migration`, `reporting`, `science` (the truth corpus), `js` (node:test), `fixtures`.

## Use the project's vocabulary

When your output names a domain concept (an issue title, a refactor proposal, a
hypothesis, a test name), use the term the project already uses. With no glossary file,
the vocabulary sources are `README.md` (measurement protocol and session format),
`docs/scientific-manual.md`, the ADRs, and the module names above.

Prefer the repo's own terms: `session`, `manifest`, `needles`, `line quality`,
`input reference`, `self-noise`, `sync source`, `wave`. Don't drift to synonyms.

If the concept you need has no home in any of those, that's a signal: either you're
inventing language the project doesn't use (reconsider) or there's a real gap
(note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than
silently overriding:

> _Contradicts ADR-0007 (identifiers, time and units), but worth reopening because…_
