"""Що відбувається із замовленням після оплати: позначити оплаченим і відправити товари в Printful."""

import os
from datetime import datetime, timezone

from sqlalchemy import select

import printful
from models import Order, db


def _lock(order_id):
    """Блокує рядок замовлення до кінця транзакції, щоб вебхук і сторінка «дякуємо»
    не обробили одну оплату двічі. Блокуємо окремим запитом: у PostgreSQL FOR UPDATE
    не можна поєднати з LEFT JOIN, яким разом із замовленням підтягуються його позиції."""
    db.session.execute(select(Order.id).where(Order.id == order_id).with_for_update())
    return db.session.get(Order, order_id, populate_existing=True)


def auto_confirm():
    """PRINTFUL_AUTO_CONFIRM=1 — оплачене замовлення одразу йде в друк.
    Інакше в Printful створюється чернетка, і ти підтверджуєш її кнопкою в адмінці."""
    return os.environ.get("PRINTFUL_AUTO_CONFIRM", "").lower() in ("1", "true", "yes")


def send_to_printful(order, confirm=False):
    """Створює замовлення в Printful. Повертає текст для адмінки. Помилку зберігає в order.printful_error."""
    items = order.printful_items
    if not items:
        return "У замовленні немає товарів Printful"
    if order.printful_order_id:
        return "Замовлення вже є в Printful"
    if not (order.address and order.country_code and order.zip_code):
        order.printful_error = "Немає повної адреси для Printful"
        return order.printful_error
    try:
        result = printful.create_order(order, items, confirm=confirm)
    except printful.PrintfulError as e:
        order.printful_error = str(e)[:300]
        return f"Не вдалося створити замовлення в Printful: {e}"
    order.printful_order_id = result.get("id")
    order.printful_status = result.get("status", "pending" if confirm else "draft")
    order.printful_error = None
    if confirm:
        return f"Замовлення №{order.printful_order_id} відправлено в Printful у друк"
    return f"Чернетку №{order.printful_order_id} створено в Printful. Підтверди її, щоб пішла в друк"


def mark_paid(order_id):
    """Позначає замовлення оплаченим і відправляє Printful-товари. Безпечно викликати кілька разів:
    і вебхук Stripe, і сторінка «дякуємо» можуть прийти одночасно."""
    order = _lock(order_id)
    if order is None or order.payment_status == "paid":
        db.session.commit()
        return order
    order.payment_status = "paid"
    order.paid_at = datetime.now(timezone.utc)
    if order.status in ("pending", "cancelled"):
        order.status = "confirmed"
    if order.printful_items and printful.is_configured():
        send_to_printful(order, confirm=auto_confirm())
    db.session.commit()
    return order


def mark_expired(order_id):
    """Покупець не оплатив за відведений час — скасовуємо замовлення."""
    order = _lock(order_id)
    if order is not None and order.payment_status == "unpaid":
        order.payment_status = "expired"
        order.status = "cancelled"
    db.session.commit()
