"""LIZKA — магазин одягу на Flask (Python 3).
Запуск:  python app.py   → http://127.0.0.1:5000
"""

import os

from flask import Flask, abort, jsonify, render_template, request, session

from products import CATEGORIES, PRODUCTS, format_price, garment_svg, get_product, get_products

app = Flask(__name__)
# Для продакшну задай свій ключ через змінну середовища SECRET_KEY
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")

# Функції, доступні в шаблонах
app.jinja_env.globals.update(garment_svg=garment_svg, format_price=format_price)


# ===== Кошик (зберігається в сесії користувача) =====
def get_cart():
    return session.setdefault("cart", [])


def cart_payload():
    """Кошик у форматі для фронтенду."""
    items = []
    total = 0
    for item in get_cart():
        p = get_product(item["id"])
        if not p:
            continue
        total += p["price"] * item["qty"]
        items.append({
            "id": p["id"], "name": p["name"], "size": item["size"], "qty": item["qty"],
            "price": format_price(p["price"]), "bg": p["bg"],
            "svg": str(garment_svg(p["shape"], p["color"])),
        })
    return {
        "items": items,
        "count": sum(i["qty"] for i in items),
        "total": format_price(total),
    }


# ===== Сторінки =====
@app.route("/")
def index():
    category = request.args.get("cat", "all")
    if category not in {c["id"] for c in CATEGORIES}:
        category = "all"
    rack = [get_product(i) for i in (1, 4, 7, 9)]
    return render_template(
        "index.html",
        categories=CATEGORIES,
        active_category=category,
        products=get_products(category),
        rack=rack,
        cart_count=sum(i["qty"] for i in get_cart()),
    )


# ===== API =====
@app.get("/api/products/<int:product_id>")
def api_product(product_id):
    p = get_product(product_id)
    if not p:
        abort(404)
    return jsonify({**p, "price_text": format_price(p["price"]), "svg": str(garment_svg(p["shape"], p["color"]))})


@app.get("/api/cart")
def api_cart():
    return jsonify(cart_payload())


@app.post("/api/cart/add")
def api_cart_add():
    data = request.get_json(silent=True) or {}
    p = get_product(int(data.get("id", 0)))
    size = data.get("size")
    if not p or size not in p["sizes"]:
        return jsonify({"error": "Невірний товар або розмір"}), 400

    cart = get_cart()
    for item in cart:
        if item["id"] == p["id"] and item["size"] == size:
            item["qty"] += 1
            break
    else:
        cart.append({"id": p["id"], "size": size, "qty": 1})
    session.modified = True
    return jsonify(cart_payload())


@app.post("/api/cart/update")
def api_cart_update():
    data = request.get_json(silent=True) or {}
    cart = get_cart()
    idx = data.get("index")
    action = data.get("action")
    if not isinstance(idx, int) or not 0 <= idx < len(cart):
        return jsonify({"error": "Немає такої позиції"}), 400

    if action == "inc":
        cart[idx]["qty"] += 1
    elif action == "dec":
        cart[idx]["qty"] -= 1
        if cart[idx]["qty"] <= 0:
            cart.pop(idx)
    elif action == "del":
        cart.pop(idx)
    else:
        return jsonify({"error": "Невідома дія"}), 400
    session.modified = True
    return jsonify(cart_payload())


@app.post("/api/checkout")
def api_checkout():
    # TODO: форма замовлення, збереження в БД, повідомлення в Telegram тощо
    return jsonify({"message": "Оформлення замовлення ще в розробці"})


if __name__ == "__main__":
    app.run(debug=True)
