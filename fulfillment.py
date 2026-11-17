"""Що відбувається із замовленням після оплати: позначити оплаченим і відправити товари в Printful."""

import csv
import io
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


def norm_name(s):
    return (s or "").strip().casefold()


def apply_printful_data(p, data):
    """Записує в товар сайту дані з Printful: привʼязку, розміри, ID варіантів.
    Назву, ціну, опис і фото на сайті не чіпає."""
    if p.printful_id != data["id"]:
        taken = Product.query.filter(Product.printful_id == data["id"], Product.id != p.id).first()
        if taken is None:
            p.printful_id = data["id"]
    p.printful_external_id = data.get("external_id")
    p.printful_name = (data.get("name") or "")[:200]
    p.sizes = ",".join(data["variants"])
    p.printful_variants = json.dumps(data["variants"])
    p.printful_variant_ext = json.dumps(data.get("variant_external") or {})
    p.printful_currency = data["currency"]


def locate_printful_product(p, listing=None):
    """Шукає товар сайту в Printful: за ID, потім за External ID, потім за назвою.
    ID змінюється, якщо товар у Printful видалили й створили наново. Повертає parse_product(...) або None."""
    lookups = [lambda: printful.get_sync_product(p.printful_id)] if p.printful_id else []
    if p.printful_external_id:
        lookups.append(lambda: printful.get_sync_product_by_external_id(p.printful_external_id))
    for lookup in lookups:
        try:
            return printful.parse_product(lookup())
        except printful.PrintfulError as e:
            if e.status != 404:
                raise
    names = {norm_name(p.printful_name), norm_name(p.name)} - {""}
    if listing is None:
        listing = printful.list_sync_products()
    for item in listing:
        if not item.get("is_ignored") and norm_name(item.get("name")) in names:
            return printful.parse_product(printful.get_sync_product(item["id"]))
    return None


def _not_found_message(item):
    msg = (f"«{item.product_name}»: у Printful немає такого товару — ні за ID, ні за External ID, ні за назвою")
    try:
        store = printful.store_info()
        msg += f". Токен підключений до магазину «{store.get('name')}» (ID {store.get('id')}, тип {store.get('type')})"
    except printful.PrintfulError:
        pass
    return msg + ". Перевір, що товар лежить саме в цьому магазині"


def refresh_variant_ids(items):
    """Перед відправкою підтягує з Printful актуальні ID варіантів за назвою розміру.
    Printful видає нові ID, якщо товар там відредагували чи перестворили,
    і тоді збережений у замовленні ID дає «Sync variant not found»."""
    fresh = {}       # product.id -> {"M": sync_variant_id}
    listing = None   # список товарів Printful, тягнемо лише якщо знадобиться
    for item in items:
        p = db.session.get(Product, item.product_id) if item.product_id else None
        if p is None or p.fulfillment != "printful":
            continue   # товар видалили з сайту — пробуємо зі збереженим ID
        if p.id not in fresh:
            try:
                data = locate_printful_product(p, listing)
            except printful.PrintfulError as e:
                raise printful.PrintfulError(f"«{item.product_name}»: {e}", status=e.status) from None
            if data is None:
                raise printful.PrintfulError(_not_found_message(item))
            apply_printful_data(p, data)
            fresh[p.id] = data["variants"]
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


# ===== CSV для імпорту замовлень у Printful (Orders → Import) =====
CSV_COLUMNS = [
    "Order ID", "Product ID", "Variant ID", "Quantity", "Full name", "Company",
    "Address line 1", "Address line 2", "State/Province/Prefecture", "City", "Country",
    "Postal/ZIP code", "Phone number",
    # Запасні колонки: числові ID з API, якщо імпорт не прийме ID з кабінету
    "Sync product ID (API)", "Sync variant ID (API)",
]
NEEDS_STATE = {"US": "США", "CA": "Канади", "JP": "Японії"}


def orders_for_export(scope="new", order_id=None):
    """Замовлення, які можна вивантажити: з товарами Printful, не скасовані, оплачені
    (або без онлайн-оплати) і ще не створені в Printful. scope="new" — ще не вивантажені в CSV."""
    q = Order.query.order_by(Order.id).filter(
        Order.status != "cancelled", db.or_(Order.payment_status.is_(None), Order.payment_status == "paid"))
    if order_id:
        q = q.filter(Order.id == order_id)
    else:
        q = q.filter(Order.printful_order_id.is_(None))
        if scope == "new":
            q = q.filter(Order.printful_exported_at.is_(None))
    return [o for o in q.all() if o.printful_items]


def build_printful_csv(orders):
    """Повертає (текст CSV, список попереджень). Перед вивантаженням підтягує з Printful актуальні ID."""
    warnings, done, listing = [], set(), None
    if printful.is_configured():
        for o in orders:
            for item in o.printful_items:
                p = db.session.get(Product, item.product_id) if item.product_id else None
                if p is None or p.fulfillment != "printful" or p.id in done:
                    continue
                done.add(p.id)
                try:
                    data = locate_printful_product(p, listing)
                except printful.PrintfulError as e:
                    warnings.append(f"«{p.name}»: не вдалося оновити ID з Printful ({e})")
                    continue
                if data is None:
                    warnings.append(f"«{p.name}»: товару немає в магазині Printful")
                else:
                    apply_printful_data(p, data)

    out = io.StringIO()
    w = csv.writer(out, lineterminator="\r\n")
    w.writerow(CSV_COLUMNS)
    for o in orders:
        if o.country_code in NEEDS_STATE:
            warnings.append(f"Замовлення №{o.id}: для {NEEDS_STATE[o.country_code]} Printful вимагає штат/провінцію — "
                            "дописати в колонку State/Province/Prefecture вручну")
        for item in o.printful_items:
            p = db.session.get(Product, item.product_id) if item.product_id else None
            product_ext = (p.printful_external_id if p else None) or ""
            variant_ext = (p.printful_ext_map.get(item.size) if p else None) or ""
            sync_vid = (p.printful_map.get(item.size) if p else None) or item.printful_variant_id or ""
            if not product_ext or not variant_ext:
                warnings.append(f"Замовлення №{o.id}, «{item.product_name} ({item.size})»: немає Product/Variant ID "
                                "з кабінету Printful — натисни «Синхронізувати з Printful» і вивантаж ще раз")
            w.writerow([
                f"lizka-{o.id}", product_ext, variant_ext, item.qty, o.customer_name, "",
                o.address or "", "", "", o.city, o.country_code or "", o.zip_code or "", o.phone or "",
                (p.printful_id if p else "") or "", sync_vid,
            ])
    return out.getvalue(), list(dict.fromkeys(warnings))
