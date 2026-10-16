# packaging — dual-EXE release + deterministic ZIP

## OVERVIEW

19 files: PyInstaller spec + PowerShell 5.1 release orchestrators + forbidden-pattern gates + frozen Todo-13 evidence spike.

## WHERE TO LOOK

| Task | Entry |
|---|---|
| Release build | `build.ps1 -Clean -Evidence <dir>`; add `-SourceArchive -HantekSource <hantek.git>` for corresponding source; `-SkipBuild -StageFrom <bundle-dir>` validates a staged bundle only |
| Bundle validation | `validate-bundle.ps1` (dot-sourced lib; forbidden-pattern scan runs before any ZIP is written) |
| Failure-mode proofs | `test-failure-modes.ps1 -Stage <bundle-dir> -Evidence <dir>` |
| Frozen smoke journey | `smoke-portable.ps1 -Zip dist\<LNT-*-win64.zip> -Evidence <dir>` — simulate → analyze → compare → selftest → experiment → statistics → backup/restore, stock PowerShell 5.1, toolchains scrubbed from PATH |
| PyInstaller spec | `lnt.spec` — windowed `LNT.exe` + console `LNT-cli.exe`, one COLLECT |
| Corresponding-source recipe | `SOURCE.txt` (asset names + version truth) |
| Frozen spike | `spike/` — probe, fake adapters, PE-import walk, allowlist v1, `build-and-probe.ps1` |

## CONVENTIONS

- PowerShell 5.1, `Set-StrictMode -Version Latest` + `$ErrorActionPreference = "Stop"`; documented exit-code contracts in headers (build: 0 ok / 2 validation / 3 artifact assertion / 4 zip+hash / 10 preflight; smoke: 0 / 10 / 20 / 30 / 40 / 50 / 60 / 70 by stage).
- Version resource built from `pyproject.toml`; no EXE icon (deliberate).
- Hantek6022API pinned via `$hantekCommit` (`e65d52b0f2…`) + `hantek-6022be.patch`; firmware sha256 pinned in `build.ps1`.
- Deterministic ZIP; `system32-allowlist.v2.json` gates system DLL imports.
- `lnt.spec` hard guard: raises if `pytest`/`_pytest` modules get selected into the PYZ.

## ANTI-PATTERNS

- Bundle must never contain: `node_modules`, `.vite`, plotly, vitest/playwright/jest, `__pycache__`, `_pytest`, `package.json`/lockfiles, tsconfig/biome/vite/vitest configs, `/frontend/`, `/bench/`, `/tests/`, any `.py`/`.pyc`/`.map` — every file must be classified or validation fails.
- UPX, one-file, Zadig, system DLLs, Node/dev/test/Plotly — deliberately forbidden.
- Smoke evidence label may ONLY be `sanitized-reference-host-verified` — never sterile / clean-VM / universal / externally-verified.
- `-SourceArchive` is forbidden when `project/.git` exists or inside a Git worktree.
- `spike/probe.py` is a frozen diagnostic — never captures or changes firmware/drivers.
- Release asset names follow `packaging/SOURCE.txt` — check it before quoting asset names anywhere else.
