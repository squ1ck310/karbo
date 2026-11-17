"""Що відбувається із замовленням після оплати: позначити оплаченим і відправити товари в Printful."""

import json
import os
import re
from datetime import datetime, timezone

from sqlalchemy import select

import printful
from models import Order, Product, db


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


def refresh_variant_ids(items):
    """Перед відправкою підтягує з Printful актуальні ID варіантів за назвою розміру.
    Printful видає варіантам нові ID, якщо товар там відредагували чи перестворили,
    і тоді збережений у замовленні ID дає «Sync variant not found»."""
    fresh = {}   # product.id -> {"M": sync_variant_id}
    for item in items:
        p = db.session.get(Product, item.product_id) if item.product_id else None
        if p is None or not p.printful_id:
            continue   # товар видалили з сайту — пробуємо зі збереженим ID
        if p.id not in fresh:
            try:
                data = printful.parse_product(printful.get_sync_product(p.printful_id))
            except printful.PrintfulError as e:
                raise printful.PrintfulError(
                    f"«{item.product_name}»: не вдалося знайти товар у Printful ({e}). "
                    "Можливо, його видалили або токен від іншого магазину") from None
            fresh[p.id] = data["variants"]
            # Заодно оновлюємо товар на сайті, як це робить синхронізація
            p.sizes = ",".join(data["variants"])
            p.printful_variants = json.dumps(data["variants"])
            p.printful_currency = data["currency"]
        vid = fresh[p.id].get(item.size)
        if vid is None:
            raise printful.PrintfulError(
                f"«{item.product_name}», розмір {item.size}: такого варіанта в Printful більше немає. "
                f"Зараз є: {', '.join(fresh[p.id]) or 'нічого'}")
        item.printful_variant_id = vid


def _name_items(message, items):
    """«Item 0: …» від Printful → «Футболка (M): …», щоб було видно, який товар."""
    def repl(m):
        i = int(m.group(1))
        return f"«{items[i].product_name} ({items[i].size})»:" if i < len(items) else m.group(0)
    return re.sub(r"Item (\d+):", repl, message)


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
        refresh_variant_ids(items)
        result = printful.create_order(order, items, confirm=confirm)
    except printful.PrintfulError as e:
        msg = _name_items(str(e), items)
        order.printful_error = msg[:300]
        return f"Не вдалося створити замовлення в Printful: {msg}"
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
