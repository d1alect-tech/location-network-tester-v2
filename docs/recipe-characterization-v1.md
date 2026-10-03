# Рецепт characterization-v1

Каноническое имя расширенного рецепта: `characterization-v1`.

Каноническое содержимое: `docs/examples/characterization-recipe-v2.json`
(schema_version 2, mode `characterization`, строго 18 блоков families в
заданном порядке, все `method_version: 1`). Проверено строгой валидацией
`CharacterizationRecipe.from_mapping` / `parse_analysis_recipe`:
round-trip `to_mapping() == mapping`, канонический sha256 — `d35f875d…`.

Точки входа (символические ссылки; номера строк — на aaade98, при правках
могут сдвинуться, ищите по именам):

- `parse_analysis_recipe` — `src/lnt/analysis_store/recipe_parse.py:21`
  (диспетчер по `schema_version`).
- `CharacterizationRecipe.from_mapping` —
  `src/lnt/analysis_store/recipe_v2.py:64` (строгий разбор без defaults).
- `CharacterizationRecipe.recipe_sha256` (property) —
  `src/lnt/analysis_store/recipe_v2.py:135` (sha256 только канонических байтов).

### Канонический pin и пересчёт

Канонический machine-checked pin живёт в
`tests/analysis/test_recipe_v2.py` — тест
`test_characterization_example_round_trips_through_public_parser`
(assert `recipe.recipe_sha256 == "d35f875d…"`; на aaade98 — строки 35-37,
комментарий над ними объясняет смену F18 `segment_samples 4096` на
`segment_duration_s 0.001`).

Пересчёт pin — из корня репозитория:

```
uv run --python 3.12 python -c "from pathlib import Path; from lnt.analysis_store import parse_analysis_recipe; from lnt.context.json_codec import decode_object; p = Path('docs/examples/characterization-recipe-v2.json'); print(parse_analysis_recipe(decode_object(p.read_text(encoding='utf-8'), p.name)).recipe_sha256)"
```

Вывод (совпадает с pin посимвольно):

```
d35f875d72a2ddee0b540b0fdbe7939c78db4e517cc687f889ed0eddf99de55f
```

### Триангуляция хешей

- `d35f875d72a2ddee0b540b0fdbe7939c78db4e517cc687f889ed0eddf99de55f` —
  **канонический** `recipe_sha256`: sha256 канонических (compact, sorted-keys)
  байтов рецепта. Это и есть authority.
- `1a9b1d4a0dd3ecfd9afea39cc41a574a7398e27cd2e5ee0c1b1754175c1ffa53` —
  sha256 **сырых байтов файла** `docs/examples/characterization-recipe-v2.json`
  (отступы, порядок ключей, переводы строк). Никогда не выдавать его за
  `recipe_sha256`: он меняется от любого редактирования файла, даже
  семантически нейтрального.

Прочие тесты — `tests/analysis/test_recipe_v2.py` (допуски не расширялись).

Сидирование: при первом использовании рецепт сохраняется через
`RecipeCatalog(<root>/.lnt/analysis-recipes/).create("characterization-v1", recipe)`
— тот же путь, что использует `src/lnt/ui/routes_analysis_v2.py`. Identity файла =
payload ID = canonical hash; `clone` для schema_version=2 отклоняется,
удаление отклоняется 409 (действующее поведение каталога, без изменений).

Плейсхолдеры method+version — из example-рецепта (locked enums в
`src/lnt/analysis_store/characterization_locked.py`, не менялись):

| family | method | v |
|---|---|---|
| f01_phase_cycle | synchronous_relative_harmonic_dft | 1 |
| f02_amplitude_time_shape | template_gain_delay_least_squares | 1 |
| f03_interharmonic_tracking | synchronous_bin_nearest_neighbor_tracks | 1 |
| f04_multicycle_periodicity | overlapping_allan_deviation_and_cycle_autocorrelation | 1 |
| f05_phase_conditioned_statistics | uniform_phase_bin_moments | 1 |
| f06_modulation_trajectories | butterworth_hilbert_analytic_trajectory | 1 |
| f07_comb_sideband_cepstrum | two_window_real_cepstrum_and_sideband_symmetry | 1 |
| f08_transient_morphology | bounded_single_damped_sinusoid_fit | 1 |
| f09_event_ordering | typed_transition_and_waiting_time_inventory | 1 |
| f10_threshold_episode_surface | phase_residual_threshold_duration_v2s_surface | 1 |
| f11_conditional_distributions | fixed_phase_band_f15_mode_empirical_distributions | 1 |
| f12_spectral_kurtosis | antoni_multiscale_stft_max_search_surrogate | 1 |
| f13_band_envelope_coactivity | phase_residual_hilbert_envelope_coactivity | 1 |
| f14_cross_channel_event_association | bidirectional_event_triggered_cross_channel_association | 1 |
| f15_interpretable_modes | deterministic_pam_fixed_k_medoids | 1 |
| f16_multiscale_memory | fft_acf_declared_recurrence_nonoverlap_fano | 1 |
| f17_cyclic_spectral_coherence | phase_residual_declared_alpha_cycle_permutation_coherence | 1 |
| f18_bicoherence_triads | declared_normalized_bicoherence_dual_surrogate | 1 |

## not_computed — стабильный reason-код

`not_computed` — стабильный reason-код «семейство ещё не реализовано»:
`Status.UNAVAILABLE` + `reason_codes=("not_computed",)` без outputs, что совпадает
с фикстурой `tests/characterization/conftest.py` (`make_bundle`: 17 плейсхолдеров
UNAVAILABLE/`not_computed`, инварианты `models.py:101-107` держат). Имя кода не
переименовывать — обязано совпадать с фикстурой.

По ADR-0008 (`docs/adr/ADR-0008-error-taxonomy.md`): ожидаемая научная
недоступность — это данные (`status` + стабильный `reason_code`), а не исключение;
вызывающие ветвятся по типу и коду, не по тексту. `not_computed` — такой код для
not-yet-implemented семейств; выполнение characterization через API пока отклоняется
422 «выполнение рецепта characterization пока не подключено» без побочных эффектов
(`tests/test_analysis_routes_v2.py:216`).

## Границы (не менялось)

- Builtin default-рецепт без изменений: `src/lnt/analysis_v2/default_recipe.py`
  (`BUILTIN_MEASUREMENT_RECIPE`, schema_version 1, mode `standard`). Обычный анализ
  не замедляется — extended анализ отдельно выбранным рецептом.
- Управление каталогом (clone/edit/delete через UI/API) — OUT, не добавлялось.
- `characterization_locked.py`, CLI, compare, `projection.py` — не тронуты.
