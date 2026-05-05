"""Pricing rule execution and rounding logic."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from ecommerce.utils.text import collapse_internal_spaces


@dataclass(frozen=True)
class PricingRule:
    rule_family: str
    parameters: dict[str, object]
    rounding_mode: str | None = None


@dataclass(frozen=True)
class PricingContext:
    source_name: str
    observed_price: Decimal
    input_price: Decimal | None = None
    source_extra_values: dict[str, str] = field(default_factory=dict)


def compute_new_price(
    rule: PricingRule,
    observed_price: Decimal,
    *,
    pricing_context: PricingContext | None = None,
) -> str:
    computed = _compute_decimal_price(rule, observed_price, pricing_context)
    if computed < Decimal("0"):
        computed = Decimal("0")

    return _apply_rounding_mode(computed, rule.rounding_mode or "nearest")


def _compute_decimal_price(
    rule: PricingRule,
    observed_price: Decimal,
    pricing_context: PricingContext | None,
) -> Decimal:
    parameters = rule.parameters

    if rule.rule_family == "fixed_offset":
        return observed_price + _decimal_parameter(parameters, "offset")

    if rule.rule_family == "percentage_discount":
        discount_percent = _decimal_parameter(parameters, "discount_percent")
        return observed_price * (Decimal("1") - (discount_percent / Decimal("100")))

    if rule.rule_family == "fixed_offset_with_floor":
        floor_value = _decimal_parameter(parameters, "floor")
        computed = observed_price + _decimal_parameter(parameters, "offset")
        return max(computed, floor_value)

    if rule.rule_family == "formula_with_rounding":
        formula = parameters.get("formula")
        if not isinstance(formula, str) or not formula.strip():
            raise ValueError("formula_with_rounding requires a non-empty parameters.formula")
        return _evaluate_formula(formula, observed_price)

    if rule.rule_family == "bestprice_store_positioning":
        return _compute_bestprice_store_positioning(rule, observed_price, pricing_context)

    raise ValueError(f"unsupported rule_family in pricing config: {rule.rule_family}")


def _apply_rounding_mode(value: Decimal, rounding_mode: str) -> str:
    integer_part = int(value.to_integral_value(rounding=ROUND_FLOOR))
    fractional_part = value - Decimal(integer_part)

    if rounding_mode == "keep_2dp":
        return _format_two_decimal_price(value)
    if rounding_mode == "floor":
        return str(integer_part)
    if rounding_mode == "ceil":
        return str(int(value.to_integral_value(rounding=ROUND_CEILING)))
    if rounding_mode == "nearest":
        return str(int(value.to_integral_value(rounding=ROUND_HALF_UP)))
    if rounding_mode == "minus_one_if_decimal_79_99":
        if Decimal("0.79") <= fractional_part <= Decimal("0.99"):
            return str(integer_part)
        return str(int(value.to_integral_value(rounding=ROUND_HALF_UP)))

    raise ValueError(f"unsupported rounding_mode in pricing config: {rounding_mode}")


def _decimal_parameter(parameters: dict[str, object], key: str) -> Decimal:
    value = parameters.get(key)
    if value is None:
        raise ValueError(f"pricing config parameter missing: {key}")
    return Decimal(str(value))


def _evaluate_formula(formula: str, observed_price: Decimal) -> Decimal:
    tree = ast.parse(formula, mode="eval")
    return _eval_ast(tree.body, observed_price)


def _eval_ast(node: ast.AST, observed_price: Decimal) -> Decimal:
    if isinstance(node, ast.BinOp):
        left = _eval_ast(node.left, observed_price)
        right = _eval_ast(node.right, observed_price)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            return left / right
        raise ValueError("unsupported operator in pricing formula")

    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        return -_eval_ast(node.operand, observed_price)

    if isinstance(node, ast.Name):
        if node.id in {"skroutz_price", "bestprice_price", "observed_price"}:
            return observed_price
        raise ValueError("pricing formula may only reference skroutz_price, bestprice_price, or observed_price")

    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return Decimal(str(node.value))

    raise ValueError("unsupported expression in pricing formula")


def _format_two_decimal_price(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


def _compute_bestprice_store_positioning(
    rule: PricingRule,
    observed_price: Decimal,
    pricing_context: PricingContext | None,
) -> Decimal:
    if pricing_context is None:
        raise ValueError("bestprice_store_positioning requires pricing context")
    if pricing_context.source_name != "bestprice":
        raise ValueError("bestprice_store_positioning requires a BestPrice enriched CSV")

    own_store = _string_parameter(rule.parameters, "own_store")
    target_gap = _decimal_parameter(rule.parameters, "target_gap")
    min_gap = _decimal_parameter(rule.parameters, "min_gap")
    max_gap = _decimal_parameter(rule.parameters, "max_gap")
    if min_gap > max_gap:
        raise ValueError("bestprice_store_positioning requires min_gap <= max_gap")

    source_extra_values = pricing_context.source_extra_values
    best_store_name = source_extra_values.get("bestprice_best_store", "")
    best_store_price = _optional_decimal_text(source_extra_values.get("bestprice_best_store_price", ""))
    next_store_price = _optional_decimal_text(source_extra_values.get("bestprice_next_store_price", ""))
    current_best_price = best_store_price if best_store_price is not None else observed_price

    if _normalize_store_name(best_store_name) == _normalize_store_name(own_store):
        if next_store_price is None:
            return current_best_price
        gap_to_next_store = next_store_price - current_best_price
        if min_gap <= gap_to_next_store <= max_gap:
            return current_best_price
        return next_store_price - target_gap

    return current_best_price - target_gap


def _normalize_store_name(value: str) -> str:
    return collapse_internal_spaces(value).casefold()


def _optional_decimal_text(value: str) -> Decimal | None:
    if not value.strip():
        return None
    return Decimal(value)


def _string_parameter(parameters: dict[str, object], key: str) -> str:
    value = parameters.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"pricing config parameter missing: {key}")
    return value.strip()
