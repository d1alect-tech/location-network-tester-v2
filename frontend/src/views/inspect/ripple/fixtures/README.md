# Фикстуры панели «Риппл / шум»

Байт-точные копии **реальных** `ripple.json`, собранных кампанией
(`.omo/evidence/ripple-noise-measurement/task-3/verify-qa-sessions/qa-root/`).
Тесты читают только их и ничего вне репозитория.

| Файл | sha256 | Источник | Зачем |
| --- | --- | --- | --- |
| `ripple-constant-zero-spectrum.json` | `63a0ef56b3ee6c860933c1b0f333d0c88865f3febcea0ab42af60b6c5f059aea` | `qa-root/constant/ripple.json` | `spectrum.availability="available"`, 5001 бин, все уровни 0 → дефект F1: доступный спектр назывался «недоступен» |
| `ripple-clip-mismatch-qc.json` | `31bea3ca75d6d031b30375982812664702f33f5146a74f96108da1c1e8a11a88` | `qa-root/clip-mismatch/ripple.json` | QC-текст 127 символов → дефект F2: строка обрезалась на 1280 px |

Правила:

- Файлы **заморожены побайтово**: sha256 обязан совпадать с оригиналом кампании,
  иначе регрессия проверяет не тот артефакт. Поэтому папка внесена в
  `files.ignore` `frontend/biome.json` — форматтер не имеет права их
  переверстать (тот же приём, что для `src/test-support/analysis-v2-fixtures/`).
- Обновление — только новой копией реального артефакта с фиксацией нового sha256
  в этой таблице и в `.omo/evidence/.../task-8/DoneClaim.json`.
- Потребители: `rippleRealArtifacts.test.ts` (vitest) и
  `rippleStability.spec.ts` (playwright, сессии `ripple-real-constant` и
  `ripple-real-clip`).
