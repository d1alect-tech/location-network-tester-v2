"""LNT — Location Network Tester.

Захват шума домашней сети (Hantek 6022BE: CH1 = X2-пробник 3 кГц–3 МГц,
CH2 = трансформатор 230:6 для формы 50 Гц), синтетический режим и анализ:
band-спектр Уэлча, метрика иголок (sigma_pk/mu_pk, P_async/P_sync),
НЧ-огибающая вершин, per-site baseline и сравнение сессий.
"""

from typing import Final

__version__: Final[str] = "0.1.0"
