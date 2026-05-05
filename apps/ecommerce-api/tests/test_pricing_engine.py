import sys
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ecommerce.pricing.engine import PricingContext, PricingRule, compute_new_price


def test_fixed_offset_rule() -> None:
    rule = PricingRule(
        rule_family="fixed_offset",
        parameters={"offset": -5},
        rounding_mode="nearest",
    )
    assert compute_new_price(rule, Decimal("178.99")) == "174"


def test_percentage_discount_rule() -> None:
    rule = PricingRule(
        rule_family="percentage_discount",
        parameters={"discount_percent": 10},
        rounding_mode="nearest",
    )
    assert compute_new_price(rule, Decimal("200.00")) == "180"


def test_fixed_offset_with_floor_rule() -> None:
    rule = PricingRule(
        rule_family="fixed_offset_with_floor",
        parameters={"offset": -10, "floor": 95},
        rounding_mode="nearest",
    )
    assert compute_new_price(rule, Decimal("100.00")) == "95"


def test_formula_with_rounding_rule_matches_sample_like_default() -> None:
    rule = PricingRule(
        rule_family="formula_with_rounding",
        parameters={"formula": "skroutz_price - 1"},
        rounding_mode="nearest",
    )
    assert compute_new_price(rule, Decimal("178.99")) == "178"
    assert compute_new_price(rule, Decimal("1200.00")) == "1199"


def test_rounding_modes_and_negative_clamp() -> None:
    assert compute_new_price(
        PricingRule("formula_with_rounding", {"formula": "skroutz_price + 0.6"}, "floor"),
        Decimal("100.00"),
    ) == "100"
    assert compute_new_price(
        PricingRule("formula_with_rounding", {"formula": "skroutz_price + 0.1"}, "ceil"),
        Decimal("100.00"),
    ) == "101"
    assert compute_new_price(
        PricingRule("formula_with_rounding", {"formula": "skroutz_price + 0.5"}, "nearest"),
        Decimal("100.00"),
    ) == "101"
    assert compute_new_price(
        PricingRule("formula_with_rounding", {"formula": "skroutz_price + 0.99"}, "minus_one_if_decimal_79_99"),
        Decimal("100.00"),
    ) == "100"
    assert compute_new_price(
        PricingRule("formula_with_rounding", {"formula": "skroutz_price - 500"}, "nearest"),
        Decimal("100.00"),
    ) == "0"


def test_keep_two_decimal_rounding_mode_supports_exact_offset_pricing() -> None:
    rule = PricingRule(
        rule_family="fixed_offset",
        parameters={"offset": "-0.10"},
        rounding_mode="keep_2dp",
    )
    assert compute_new_price(rule, Decimal("171.90")) == "171.80"


def test_bestprice_store_positioning_undercuts_market_when_own_store_is_not_best() -> None:
    rule = PricingRule(
        rule_family="bestprice_store_positioning",
        parameters={
            "own_store": "eTranoulis",
            "target_gap": "0.10",
            "min_gap": "0.10",
            "max_gap": "1.00",
        },
        rounding_mode="keep_2dp",
    )

    new_price = compute_new_price(
        rule,
        Decimal("210.00"),
        pricing_context=PricingContext(
            source_name="bestprice",
            observed_price=Decimal("210.00"),
            source_extra_values={
                "bestprice_best_store": "Competitor A",
                "bestprice_best_store_price": "210.00",
                "bestprice_next_store": "Competitor B",
                "bestprice_next_store_price": "212.00",
            },
        ),
    )

    assert new_price == "209.90"


def test_bestprice_store_positioning_keeps_live_price_when_own_store_is_best_within_gap_window() -> None:
    rule = PricingRule(
        rule_family="bestprice_store_positioning",
        parameters={
            "own_store": "eTranoulis",
            "target_gap": "0.10",
            "min_gap": "0.10",
            "max_gap": "1.00",
        },
        rounding_mode="keep_2dp",
    )

    new_price = compute_new_price(
        rule,
        Decimal("397.00"),
        pricing_context=PricingContext(
            source_name="bestprice",
            observed_price=Decimal("397.00"),
            source_extra_values={
                "bestprice_best_store": "eTranoulis",
                "bestprice_best_store_price": "397.00",
                "bestprice_next_store": "Competitor A",
                "bestprice_next_store_price": "397.20",
            },
        ),
    )

    assert new_price == "397.00"


def test_bestprice_store_positioning_can_raise_price_when_own_store_gap_is_too_large() -> None:
    rule = PricingRule(
        rule_family="bestprice_store_positioning",
        parameters={
            "own_store": "eTranoulis",
            "target_gap": "0.10",
            "min_gap": "0.10",
            "max_gap": "1.00",
        },
        rounding_mode="keep_2dp",
    )

    new_price = compute_new_price(
        rule,
        Decimal("397.00"),
        pricing_context=PricingContext(
            source_name="bestprice",
            observed_price=Decimal("397.00"),
            source_extra_values={
                "bestprice_best_store": "eTranoulis",
                "bestprice_best_store_price": "397.00",
                "bestprice_next_store": "Competitor A",
                "bestprice_next_store_price": "399.50",
            },
        ),
    )

    assert new_price == "399.40"
