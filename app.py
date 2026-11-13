"""LIZKA — магазин одягу на Flask (Python 3).
Локально:  python app.py   → http://127.0.0.1:5000   (адмінка: /admin)
На Render: gunicorn app:app  (див. render.yaml)
"""

import os
import re
import secrets

from flask import Flask, abort, jsonify, render_template, request, session

from admin import admin_bp
from models import Order, OrderItem, Product, db
from products import CATEGORIES, SEED_PRODUCTS, format_price, garment_svg


def database_url():
    """Render дає адресу виду postgres://..., а SQLAlchemy з psycopg 3 хоче postgresql+psycopg://..."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return "sqlite:///lizka.db"  # локально: файл instance/lizka.db
    return re.sub(r"^postgres(ql)?://", "postgresql+psycopg://", url)


app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "dev-change-me"),
    SQLALCHEMY_DATABASE_URI=database_url(),
    SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},  # Render може перезапускати БД
)
# Render сам ставить змінну RENDER=true — там HTTPS, тож cookie тільки по HTTPS
if os.environ.get("RENDER"):
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax")

db.init_app(app)
app.register_blueprint(admin_bp)
app.jinja_env.globals.update(garment_svg=garment_svg, format_price=format_price)


# ===== Створення таблиць і стартові товари =====
def init_db():
    with app.app_context():
        db.create_all()
        if not db.session.query(Product.id).first():
            for p in SEED_PRODUCTS:
                data = {k: v for k, v in p.items() if k != "id"}
                data["sizes"] = ",".join(p["sizes"])
                db.session.add(Product(**data))
            db.session.commit()
        # Закриваємо з'єднання до того, як gunicorn розгалузить воркери (--preload)
        db.engine.dispose()


init_db()


# ===== CSRF-токен для форм і fetch-запитів =====
def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def check_csrf():
    if request.method == "POST":
        sent = request.headers.get("X-CSRF-Token") or request.form.get("csrf")
        if not sent or sent != session.get("csrf"):
            abort(400, "Невірний CSRF-токен. Онови сторінку.")


# ===== Кошик (зберігається в сесії користувача) =====
def get_cart():
    return session.setdefault("cart", [])


def cart_lines():
    """Позиції кошика разом з актуальними товарами з БД. Неактивні товари викидаються."""
    lines = []
    for item in get_cart():
        p = db.session.get(Product, item["id"])
        if p and p.is_active and item["size"] in p.size_list:
            lines.append((item, p))
    return lines


def cart_payload():
    lines = cart_lines()
    return {
        "items": [{
            "id": p.id, "name": p.name, "size": i["size"], "qty": i["qty"],
            "price": format_price(p.price), "bg": p.bg, "svg": str(garment_svg(p.shape, p.color)),
        } for i, p in lines],
        "count": sum(i["qty"] for i, _ in lines),
        "total": format_price(sum(i["qty"] * p.price for i, p in lines)),
    }


def json_error(message, code=400):
    return jsonify({"error": message}), code


# ===== Сторінки =====
@app.route("/")
def index():
    category = request.args.get("cat", "all")
    if category not in {c["id"] for c in CATEGORIES}:
        category = "all"

    query = Product.query.filter_by(is_active=True)
    if category != "all":
        query = query.filter_by(category=category)
    products = query.order_by(Product.id).all()
    rack = Product.query.filter_by(is_active=True).order_by(Product.id).limit(4).all()

    return render_template(
        "index.html",
        categories=CATEGORIES,
        active_category=category,
        products=products,
        rack=rack,
        cart_count=sum(i["qty"] for i, _ in cart_lines()),
    )


@app.get("/healthz")
def healthz():
    """Перевірка, що сервер живий (Render її пінгує)."""
    return "ok"


# ===== API =====
@app.get("/api/products/<int:product_id>")
def api_product(product_id):
    p = db.session.get(Product, product_id)
    if not p or not p.is_active:
        abort(404)
    return jsonify({
        "id": p.id, "name": p.name, "desc": p.desc, "sizes": p.size_list, "bg": p.bg,
        "price_text": format_price(p.price), "svg": str(garment_svg(p.shape, p.color)),
    })


@app.get("/api/cart")
def api_cart():
    return jsonify(cart_payload())


@app.post("/api/cart/add")
def api_cart_add():
    data = request.get_json(silent=True) or {}
    p = db.session.get(Product, int(data.get("id") or 0))
    size = data.get("size")
    if not p or not p.is_active or size not in p.size_list:
        return json_error("Невірний товар або розмір")

    cart = get_cart()
    for item in cart:
        if item["id"] == p.id and item["size"] == size:
            item["qty"] = min(item["qty"] + 1, 20)
            break
    else:
        cart.append({"id": p.id, "size": size, "qty": 1})
    session.modified = True
    return jsonify(cart_payload())


@app.post("/api/cart/update")
def api_cart_update():
    data = request.get_json(silent=True) or {}
    # Працюємо з очищеним кошиком, щоб індекси збігалися з тим, що бачить користувач
    session["cart"] = cart = [i for i, _ in cart_lines()]
    idx, action = data.get("index"), data.get("action")
    if not isinstance(idx, int) or not 0 <= idx < len(cart):
        return json_error("Немає такої позиції")

    if action == "inc":
        cart[idx]["qty"] = min(cart[idx]["qty"] + 1, 20)
    elif action == "dec":
        cart[idx]["qty"] -= 1
        if cart[idx]["qty"] <= 0:
            cart.pop(idx)
    elif action == "del":
        cart.pop(idx)
    else:
        return json_error("Невідома дія")
    session.modified = True
    return jsonify(cart_payload())


PHONE_RE = re.compile(r"^\+?[\d\s\-()]{10,18}$")


@app.post("/api/checkout")
def api_checkout():
    lines = cart_lines()
    if not lines:
        return json_error("Кошик порожній")

    data = request.get_json(silent=True) or {}
    form = {k: str(data.get(k, "")).strip() for k in ("name", "phone", "city", "branch", "comment")}
    errors = {}
    if len(form["name"]) < 2:
        errors["name"] = "Вкажіть ім'я та прізвище"
    if not PHONE_RE.match(form["phone"]):
        errors["phone"] = "Вкажіть телефон у форматі +380..."
    if len(form["city"]) < 2:
        errors["city"] = "Вкажіть місто"
    if not form["branch"]:
        errors["branch"] = "Вкажіть відділення Нової Пошти"
    if errors:
        return jsonify({"error": "Перевірте поля форми", "fields": errors}), 400

    order = Order(
        customer_name=form["name"][:120], phone=form["phone"][:30], city=form["city"][:80],
        np_branch=form["branch"][:120], comment=form["comment"][:1000],
        total=sum(i["qty"] * p.price for i, p in lines),
    )
    for i, p in lines:
        order.items.append(OrderItem(product_id=p.id, product_name=p.name, size=i["size"], price=p.price, qty=i["qty"]))
    db.session.add(order)
    db.session.commit()

    session["cart"] = []
    return jsonify({"message": f"Замовлення №{order.id} прийнято. Ми зателефонуємо для підтвердження.", "order_id": order.id})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=not os.environ.get("RENDER"))
