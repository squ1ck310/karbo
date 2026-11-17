"""Клієнт Printful API (v1) і синхронізація товарів.

Потрібні змінні середовища:
  PRINTFUL_TOKEN     — Private Token з developers.printful.com (scopes: sync_products, orders)
  PRINTFUL_STORE_ID  — тільки якщо токен рівня акаунта (Account level), а не магазину
"""

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

API_URL = "https://api.printful.com"
TIMEOUT = 20


class PrintfulError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status   # HTTP-код відповіді Printful (404 — не знайдено), якщо є


def is_configured():
    return bool(os.environ.get("PRINTFUL_TOKEN"))


def _request(method, path, body=None, params=None):
    """Один запит до API. Повертає (result, paging)."""
    token = os.environ.get("PRINTFUL_TOKEN")
    if not token:
        raise PrintfulError("Не задано PRINTFUL_TOKEN (змінна середовища)")
    url = API_URL + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "LizkaShop/1.0"}
    store_id = os.environ.get("PRINTFUL_STORE_ID")
    if store_id:
        headers["X-PF-Store-Id"] = store_id
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise PrintfulError(_error_message(e), status=e.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise PrintfulError(f"Немає зʼєднання з Printful: {e}") from None
    return payload.get("result"), payload.get("paging")


def _error_message(e):
    try:
        payload = json.loads(e.read().decode())
        err = payload.get("error")
        msg = err.get("message") if isinstance(err, dict) else None
        msg = msg or payload.get("result") or str(e)
    except Exception:
        msg = str(e)
    if e.code == 401:
        return "Printful не прийняв токен (401). Перевір PRINTFUL_TOKEN"
    if e.code == 403:
        return f"Токену бракує прав (403): {msg}. Потрібні scopes sync_products і orders"
    return f"Printful: {msg} (код {e.code})"


# ===== Товари =====
def list_sync_products():
    """Усі товари магазину Printful (з пагінацією)."""
    items, offset = [], 0
    while True:
        result, paging = _request("GET", "/store/products", params={"offset": offset, "limit": 100})
        items += result or []
        if not paging or offset + 100 >= paging.get("total", 0):
            return items
        offset += 100


def get_sync_product(sync_product_id):
    result, _ = _request("GET", f"/store/products/{sync_product_id}")
    return result


def get_sync_product_by_external_id(external_id):
    """Товар за External ID — той, що в кабінеті Printful виглядає як #6afba329ba5f06."""
    ext = urllib.parse.quote(str(external_id).lstrip("#"), safe="")
    result, _ = _request("GET", f"/store/products/@{ext}")
    return result


def store_info():
    """До якого магазину Printful підключений токен: {"id", "name", "type"}."""
    result, _ = _request("GET", "/store")
    return result or {}


CATEGORY_KEYWORDS = [
    ("hoodies", ("hoodie", "sweatshirt", "crewneck", "zip")),
    ("outer", ("jacket", "windbreaker", "bomber", "coat", "vest")),
    ("dresses", ("dress", "skirt")),
    ("pants", ("pants", "joggers", "sweatpants", "shorts", "leggings", "trousers")),
    ("tees", ("t-shirt", "tee", "tank", "shirt", "top", "polo", "long sleeve")),
]
SHAPE_FOR_CATEGORY = {"tees": "tee", "hoodies": "hoodie", "pants": "pants", "dresses": "dress", "outer": "jacket"}


def guess_category(*names):
    text = " ".join(n or "" for n in names).lower()
    for cat, words in CATEGORY_KEYWORDS:
        if any(w in text for w in words):
            return cat
    return "tees"


def variant_size_color(v):
    """(розмір, колір) варіанта. Старі відповіді API мають їх лише в назві: "Футболка / Black / M"."""
    size, color = v.get("size"), v.get("color")
    if not size and not color:
        parts = [p.strip() for p in (v.get("name") or "").split("/")]
        size = parts[-1] if len(parts) > 1 else (v.get("name") or str(v.get("id")))
        color = parts[-2] if len(parts) > 2 else None
    return size, color


def variant_label(size, color, multi_color):
    """Що покупець бачить як «розмір»: 'M' або 'Black / M', якщо в товару кілька кольорів."""
    label = f"{color} / {size}" if multi_color and color else (size or color or "")
    return label.replace(",", " ")[:40]   # кома ламає список розмірів


def parse_product(detail):
    """Перетворює відповідь /store/products/{id} на зручний словник."""
    sp = detail["sync_product"]
    variants = [v for v in detail.get("sync_variants", []) if not v.get("is_ignored")]
    parsed = [(v, *variant_size_color(v)) for v in variants]
    multi = len({color for _, _, color in parsed if color}) > 1
    mapping, ext_mapping, prices, previews = {}, {}, [], []
    for v, size, color in parsed:
        label = variant_label(size, color, multi)
        if label in mapping:
            continue
        mapping[label] = v["id"]
        ext_mapping[label] = v.get("external_id")
        try:
            prices.append(float(v.get("retail_price") or 0))
        except ValueError:
            pass
        for f in v.get("files") or []:
            if f.get("type") == "preview" and f.get("preview_url") and f["preview_url"] not in previews:
                previews.append(f["preview_url"])
    catalog_name = (variants[0].get("product") or {}).get("name", "") if variants else ""
    category = guess_category(sp.get("name"), catalog_name)
    return {
        "id": sp["id"],
        "external_id": sp.get("external_id"),
        "name": sp.get("name") or f"Printful #{sp['id']}",
        "thumbnail": sp.get("thumbnail_url"),
        "variants": mapping,
        "variant_external": ext_mapping,   # {"M": External ID варіанта, як у кабінеті Printful}
        "currency": (variants[0].get("currency") if variants else None) or "",
        "price": max(prices) if prices else 0,
        "previews": previews[:6],
        "category": category,
        "shape": SHAPE_FOR_CATEGORY[category],
    }


# ===== Замовлення =====
def create_order(order, items, confirm=False):
    """Створює замовлення в Printful. confirm=False — ЧЕРНЕТКА: у друк не йде, гроші не списуються,
    доки її не підтвердять. confirm=True — одразу в друк, Printful списує оплату з твого Wallet.
    external_id захищає від дублів."""
    body = {
        "external_id": f"lizka-{order.id}",
        "recipient": {
            "name": order.customer_name,
            "address1": order.address,
            "city": order.city,
            "country_code": order.country_code,
            "zip": order.zip_code,
            "phone": order.phone,
            "email": order.email,
        },
        "items": [{"sync_variant_id": i.printful_variant_id, "quantity": i.qty} for i in items],
    }
    result, _ = _request("POST", "/orders", body=body, params={"confirm": "true" if confirm else "false"})
    return result


def create_draft_order(order, items):
    return create_order(order, items, confirm=False)


def confirm_order(printful_order_id):
    """Підтверджує чернетку: вона йде в друк, Printful списує оплату."""
    result, _ = _request("POST", f"/orders/{printful_order_id}/confirm")
    return result


def get_order(external_id):
    result, _ = _request("GET", f"/orders/@{external_id}")
    return result
