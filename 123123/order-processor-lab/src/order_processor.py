from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum

logger = logging.getLogger(__name__)


def _to_decimal(value: object, field_name: str) -> Decimal:
    if isinstance(value, Decimal):
        decimal_value = value
    else:
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise TypeError(f"{field_name} must be numeric") from exc

    if not decimal_value.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return decimal_value


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _normalize_percentage(value: object, field_name: str) -> Decimal:
    percentage = _to_decimal(value, field_name)
    if percentage < 0:
        raise ValueError(f"{field_name} cannot be negative")
    if percentage <= 1:
        return percentage
    if percentage <= 100:
        return percentage / Decimal("100")
    raise ValueError(f"{field_name} must be between 0 and 100")


def _normalize_currency(value: object, field_name: str) -> Decimal:
    currency = _to_decimal(value, field_name)
    if currency < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return _money(currency)


class OrderStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class OrderItem:
    sku: str
    name: str
    quantity: int = 1
    unit_price: Decimal | int | float | str = 0
    discount_rate: Decimal | int | float | str = 0

    def __post_init__(self) -> None:
        if not self.sku or not str(self.sku).strip():
            raise ValueError("sku cannot be empty")
        if not self.name or not str(self.name).strip():
            raise ValueError("name cannot be empty")

        quantity = int(self.quantity)
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        self.quantity = quantity
        self.unit_price = _normalize_currency(self.unit_price, "unit_price")
        self.discount_rate = _normalize_percentage(self.discount_rate, "discount_rate")

    @property
    def subtotal(self) -> Decimal:
        return _money(self.unit_price * self.quantity)

    @property
    def discounted_subtotal(self) -> Decimal:
        discount = self.subtotal * self.discount_rate
        return _money(self.subtotal - discount)

    def to_dict(self) -> dict[str, object]:
        return {
            "sku": self.sku,
            "name": self.name,
            "quantity": self.quantity,
            "unit_price": self.unit_price,
            "discount_rate": self.discount_rate,
        }


@dataclass(slots=True)
class Order:
    order_id: str
    customer_id: str | None = None
    items: list[OrderItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    tax_rate: Decimal | int | float | str = 0
    shipping_cost: Decimal | int | float | str = 0
    discount_amount: Decimal | int | float | str = 0

    def __post_init__(self) -> None:
        if not self.order_id or not str(self.order_id).strip():
            raise ValueError("order_id cannot be empty")

        self.tax_rate = _normalize_percentage(self.tax_rate, "tax_rate")
        self.shipping_cost = _normalize_currency(self.shipping_cost, "shipping_cost")
        self.discount_amount = _normalize_currency(self.discount_amount, "discount_amount")

    def add_item(self, item: OrderItem) -> None:
        if not isinstance(item, OrderItem):
            raise TypeError("item must be an OrderItem")
        self.items.append(item)

    def remove_item(self, sku: str) -> OrderItem | None:
        for index, item in enumerate(self.items):
            if item.sku == sku:
                return self.items.pop(index)
        return None

    def empty(self) -> bool:
        return not self.items

    def to_dict(self) -> dict[str, object]:
        return {
            "order_id": self.order_id,
            "customer_id": self.customer_id,
            "items": [item.to_dict() for item in self.items],
            "status": self.status.value,
            "tax_rate": self.tax_rate,
            "shipping_cost": self.shipping_cost,
            "discount_amount": self.discount_amount,
        }


class OrderProcessor:
    """Basic order processing operations with validation and totals."""

    @staticmethod
    def calculate_subtotal(order: Order) -> Decimal:
        if order.empty():
            return Decimal("0.00")
        subtotal = sum((item.discounted_subtotal for item in order.items), Decimal("0.00"))
        return _money(subtotal)

    @staticmethod
    def calculate_tax(order: Order) -> Decimal:
        subtotal = OrderProcessor.calculate_subtotal(order)
        taxable_total = subtotal - order.discount_amount
        return _money(taxable_total * order.tax_rate)

    @staticmethod
    def calculate_total(order: Order) -> Decimal:
        subtotal = OrderProcessor.calculate_subtotal(order)
        tax = OrderProcessor.calculate_tax(order)
        total = subtotal - order.discount_amount + tax + order.shipping_cost
        return _money(total)

    @staticmethod
    def validate_order(order: Order) -> bool:
        if order.empty():
            raise ValueError("order must contain at least one item")

        for item in order.items:
            if not isinstance(item, OrderItem):
                raise TypeError("order items must be OrderItem instances")
            if item.quantity <= 0:
                raise ValueError(f"item {item.sku} quantity must be positive")
            if item.unit_price < 0:
                raise ValueError(f"item {item.sku} unit_price cannot be negative")

        if order.discount_amount > OrderProcessor.calculate_subtotal(order):
            raise ValueError("discount_amount exceeds subtotal")

        logger.info("Validated order %s", order.order_id)
        return True

    @staticmethod
    def process(order: Order) -> Order:
        OrderProcessor.validate_order(order)
        order.status = OrderStatus.PROCESSING
        logger.info("Processing order %s", order.order_id)
        return order

    @staticmethod
    def submit_order(order: Order) -> Order:
        return OrderProcessor.process(order)

    @staticmethod
    def cancel_order(order: Order) -> Order:
        if order.status == OrderStatus.CANCELLED:
            logger.info("Order %s already cancelled", order.order_id)
            return order
        order.status = OrderStatus.CANCELLED
        logger.info("Cancelled order %s", order.order_id)
        return order

    @staticmethod
    def mark_paid(order: Order) -> Order:
        if not OrderProcessor.validate_order(order):
            raise ValueError("order is invalid")
        order.status = OrderStatus.PAID
        logger.info("Marked order %s as paid", order.order_id)
        return order


def create_order(
    *items: OrderItem,
    order_id: str,
    customer_id: str | None = None,
    tax_rate: Decimal | int | float | str = 0,
    shipping_cost: Decimal | int | float | str = 0,
    discount_amount: Decimal | int | float | str = 0,
) -> Order:
    order = Order(
        order_id=order_id,
        customer_id=customer_id,
        items=list(items),
        tax_rate=tax_rate,
        shipping_cost=shipping_cost,
        discount_amount=discount_amount,
    )
    return order


def calculate_total(order: Order) -> Decimal:
    return OrderProcessor.calculate_total(order)


def validate_order(order: Order) -> bool:
    return OrderProcessor.validate_order(order)
