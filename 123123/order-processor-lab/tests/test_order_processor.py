from decimal import Decimal

import pytest

from src.order_processor import Order, OrderItem, OrderProcessor, OrderStatus


def test_order_item_applies_discount_and_subtotal() -> None:
    item = OrderItem("SKU-1", "Widget", quantity=2, unit_price="10.00", discount_rate=0.1)

    assert item.subtotal == Decimal("20.00")
    assert item.discounted_subtotal == Decimal("18.00")


def test_order_total_includes_tax_and_shipping() -> None:
    order = Order(
        order_id="ORD-100",
        items=[
            OrderItem("SKU-1", "Widget", quantity=2, unit_price=10, discount_rate=0.1),
            OrderItem("SKU-2", "Gadget", quantity=1, unit_price="5.50"),
        ],
        tax_rate=0.2,
        shipping_cost="4.75",
    )

    subtotal = OrderProcessor.calculate_subtotal(order)
    assert subtotal == Decimal("28.50")
    assert OrderProcessor.calculate_tax(order) == Decimal("5.70")
    assert OrderProcessor.calculate_total(order) == Decimal("38.95")


def test_validate_order_rejects_empty_orders_and_invalid_items() -> None:
    empty_order = Order(order_id="ORD-EMPTY")
    with pytest.raises(ValueError, match="at least one item"):
        OrderProcessor.validate_order(empty_order)

    bad_item = OrderItem("SKU-3", "Broken", quantity=0, unit_price="9.99")
    order_with_bad_item = Order(order_id="ORD-BAD", items=[bad_item])
    with pytest.raises(ValueError, match="quantity"):
        OrderProcessor.validate_order(order_with_bad_item)


def test_order_processor_process_updates_status() -> None:
    order = Order(
        order_id="ORD-200",
        items=[OrderItem("SKU-7", "Book", quantity=1, unit_price="12.00")],
    )

    processed = OrderProcessor.process(order)

    assert processed is order
    assert processed.status == OrderStatus.PROCESSING


def test_order_discount_amount_cannot_exceed_subtotal() -> None:
    order = Order(
        order_id="ORD-300",
        items=[OrderItem("SKU-9", "Light", quantity=1, unit_price="10.00")],
        discount_amount="20.00",
    )

    with pytest.raises(ValueError, match="discount_amount exceeds subtotal"):
        OrderProcessor.validate_order(order)
