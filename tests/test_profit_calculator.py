import pytest

import profit_calculator as pc


def test_effective_unit_cost():
    assert pc.effective_unit_cost(10, 2.5) == 12.5


def test_compute_fee_amount_percent():
    assert pc.compute_fee_amount(100, None, 15) == 15.0


def test_compute_fee_amount_absolute():
    assert pc.compute_fee_amount(100, 8.5, None) == 8.5


def test_compute_fee_amount_conflict():
    with pytest.raises(ValueError):
        pc.compute_fee_amount(100, 1.0, 5.0)


def test_compute_fee_amount_missing():
    with pytest.raises(ValueError):
        pc.compute_fee_amount(100, None, None)


def test_unit_profit():
    assert pc.unit_profit(30, 10, 5) == 15


def test_margin_and_roi():
    assert pc.margin_pct(7, 20) == pytest.approx(35.0)
    assert pc.roi_pct(7, 10) == pytest.approx(70.0)
    assert pc.margin_pct(1, 0) is None
    assert pc.roi_pct(1, 0) is None


def test_break_even_units():
    assert pc.break_even_units(100, 25) == 4
    assert pc.break_even_units(0, 10) is None
    assert pc.break_even_units(100, 0) is None
    assert pc.break_even_units(100, -1) is None


def test_format_money():
    assert pc.format_money(12.3, "USD") == "$12.30"
    assert pc.format_money(12.3, "eur") == "12.30 EUR"


def test_run_calculation_absolute_fees():
    res = pc.run_calculation(
        currency="USD",
        product_cost=10,
        shipping_per_unit=0,
        selling_price=20,
        fees_absolute=3,
        fee_percent=None,
        fixed_one_time_cost=100,
    )
    assert res.profit == 7
    assert res.margin == pytest.approx(35.0)
    assert res.roi == pytest.approx(70.0)
    assert res.break_even == 15


def test_run_calculation_fee_percent():
    res = pc.run_calculation(
        currency="USD",
        product_cost=10,
        shipping_per_unit=2,
        selling_price=20,
        fees_absolute=None,
        fee_percent=10,
        fixed_one_time_cost=0,
    )
    assert res.landed_cost == 12
    assert res.fee_amount == pytest.approx(2.0)
    assert res.profit == pytest.approx(6.0)


def test_run_calculation_rejects_negative_shipping():
    with pytest.raises(ValueError):
        pc.run_calculation(
            currency="USD",
            product_cost=10,
            shipping_per_unit=-1,
            selling_price=20,
            fees_absolute=1,
            fee_percent=None,
            fixed_one_time_cost=0,
        )


def test_append_csv_writes_header_once(tmp_path):
    p = tmp_path / "out.csv"
    res = pc.run_calculation(
        currency="USD",
        product_cost=1,
        shipping_per_unit=0,
        selling_price=10,
        fees_absolute=1,
        fee_percent=None,
        fixed_one_time_cost=0,
    )
    pc.append_csv(str(p), res)
    text = p.read_text(encoding="utf-8")
    assert "timestamp_utc" in text
    assert text.count("timestamp_utc") == 1
    pc.append_csv(str(p), res)
    text2 = p.read_text(encoding="utf-8")
    assert text2.count("timestamp_utc") == 1


def test_main_batch_smoke(capsys):
    pc.main(
        [
            "--cost",
            "10",
            "--price",
            "20",
            "--fees",
            "3",
        ]
    )
    out = capsys.readouterr().out
    assert "Profit" in out
    assert "$7.00" in out
