"""Formato de importes y escala de las gráficas del Dashboard."""

import pytest

pytest.importorskip("PySide6")

from ui.pages.dashboard_charts import compact_money, nice_step, whole_money  # noqa: E402


@pytest.mark.parametrize("value, expected", [
    (0, "0 €"),
    (950, "950 €"),
    (1_000, "1 k€"),
    (47_546.97, "47,5 k€"),
    (50_000, "50 k€"),
    (120_480, "120 k€"),
    (1_250_000, "1,2 M€"),
    (-34_200, "-34,2 k€"),
])
def test_compact_money(value, expected):
    assert compact_money(value) == expected


def test_whole_money():
    assert whole_money(112_978.10) == "112.978 €"
    assert whole_money(-1_234.5) == "-1.234 €"
    assert whole_money(0) == "0 €"


@pytest.mark.parametrize("span, expected", [
    (120_480, 50_000),   # 4 líneas: 0, 50k, 100k, 150k
    (10, 2.5),
    (1, 0.25),
    (3_000_000, 1_000_000),
])
def test_nice_step(span, expected):
    assert nice_step(span) == pytest.approx(expected)
