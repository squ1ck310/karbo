"""LIZKA — магазин одягу на Flask (Python 3).
Локально:  python app.py   → http://127.0.0.1:5000   (адмінка: /admin)
На Render: gunicorn app:app  (див. render.yaml)
"""

import os
import re
import secrets

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, session, url_for
from werkzeug.middleware.proxy_fix import ProxyFix

from admin import admin_bp
import fulfillment
import payments
from models import Order, OrderItem, Product, ProductImage, db, migrate
from products import CATEGORIES, CURRENCIES, SEED_PRODUCTS, format_price, format_totals, garment_svg, image_url, product_media, sum_by_currency


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
    MAX_CONTENT_LENGTH=60 * 1024 * 1024,                # загальний ліміт запиту (кілька фото разом)
)
# Render сам ставить змінну RENDER=true — там HTTPS, тож cookie тільки по HTTPS
if os.environ.get("RENDER"):
    app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_SAMESITE="Lax")
    # Render приймає HTTPS і передає запит далі по HTTP; без цього посилання для Stripe були б http://
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

db.init_app(app)
app.register_blueprint(admin_bp)
app.jinja_env.globals.update(garment_svg=garment_svg, format_price=format_price, format_totals=format_totals,
                              product_media=product_media, image_url=image_url, CURRENCIES=CURRENCIES)


@app.errorhandler(413)
def too_large(_e):
    from flask import flash, redirect
    if request.path.startswith("/admin"):
        flash("Файли завеликі: разом можна завантажити до 60 МБ за раз")
        return redirect(request.referrer or "/admin/products")
    return json_error("Запит завеликий", 413)


# ===== Створення таблиць і стартові товари =====
def init_db():
    with app.app_context():
        db.create_all()
        migrate(db.engine)
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


# Ці адреси викликає не браузер покупця, а сервіси ззовні (у них свій захист — підпис запиту)
CSRF_EXEMPT = {"/stripe/webhook"}


@app.before_request
def check_csrf():
    if request.method == "POST" and request.path not in CSRF_EXEMPT:
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
        if not p or not p.is_active or item["size"] not in p.size_list:
            continue
        if p.is_printful and item["size"] not in p.printful_map:
            continue
        lines.append((item, p))
    return lines


def cart_payload():
    lines = cart_lines()
    return {
        "items": [{
            "id": p.id, "name": p.name, "size": i["size"], "qty": i["qty"],
            "price": format_price(p.price, p.currency), "bg": p.bg,
            "media": str(product_media(p)), "has_photo": bool(p.main_image),
        } for i, p in lines],
        "count": sum(i["qty"] for i, _ in lines),
        "needs_address": any(p.is_printful for _, p in lines),
        "total": format_totals(sum_by_currency((i["qty"] * p.price, p.currency) for i, p in lines)),
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
        "price_text": format_price(p.price, p.currency), "svg": str(garment_svg(p.shape, p.color)),
        "images": [image_url(img) for img in p.images],
    })


@app.get("/img/<int:image_id>.webp")
def product_image(image_id):
    img = db.session.get(ProductImage, image_id) or abort(404)
    if img.url:
        return redirect(img.url)
    resp = make_response(img.data)
    resp.headers["Content-Type"] = img.mimetype
    # Фото з певним id ніколи не змінюється, тож браузер може кешувати його назавжди
    resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return resp


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
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Куди можна замовити товари Printful (Україна — лише з латвійської фабрики й не всі області)
COUNTRIES = {
    "UA": "Україна", "PL": "Польща", "DE": "Німеччина", "CZ": "Чехія", "SK": "Словаччина",
    "LT": "Литва", "LV": "Латвія", "EE": "Естонія", "RO": "Румунія", "HU": "Угорщина",
    "AT": "Австрія", "IT": "Італія", "ES": "Іспанія", "FR": "Франція", "NL": "Нідерланди",
    "GB": "Велика Британія", "US": "США", "CA": "Канада",
}
app.jinja_env.globals["COUNTRIES"] = COUNTRIES


@app.post("/api/checkout")
def api_checkout():
    lines = cart_lines()
    if not lines:
        return json_error("Кошик порожній")

    data = request.get_json(silent=True) or {}
    fields = ("name", "phone", "city", "branch", "comment", "email", "country", "address", "zip")
    form = {k: str(data.get(k, "")).strip() for k in fields}
    needs_address = any(p.is_printful for _, p in lines)
    errors = {}
    if len(form["name"]) < 2:
        errors["name"] = "Вкажіть ім'я та прізвище"
    if not PHONE_RE.match(form["phone"]):
        errors["phone"] = "Вкажіть телефон у форматі +380..."
    if len(form["city"]) < 2:
        errors["city"] = "Вкажіть місто"
    if needs_address:
        # Товари Printful їдуть кур'єром на повну адресу, а не на відділення Нової Пошти
        if form["country"] not in COUNTRIES:
            errors["country"] = "Оберіть країну"
        if len(form["address"]) < 5:
            errors["address"] = "Вкажіть вулицю, будинок і квартиру"
        if not re.fullmatch(r"[A-Za-z0-9 \-]{3,10}", form["zip"]):
            errors["zip"] = "Вкажіть поштовий індекс"
        if not EMAIL_RE.match(form["email"]):
            errors["email"] = "Вкажіть email, туди прийде трек-номер"
    elif not form["branch"]:
        errors["branch"] = "Вкажіть відділення Нової Пошти"
    if errors:
        return jsonify({"error": "Перевірте поля форми", "fields": errors}), 400

    currencies = {p.currency for _, p in lines}
    online = payments.is_configured()
    if online and len(currencies) > 1:
        return json_error("Оплатити одним платежем можна лише товари в одній валюті. "
                          "Оформи товари в різних валютах окремими замовленнями")

    order = Order(
        customer_name=form["name"][:120], phone=form["phone"][:30], city=form["city"][:80],
        np_branch="" if needs_address else form["branch"][:120], comment=form["comment"][:1000],
        # total — сума, якщо всі товари в одній валюті; для змішаних дивись order.totals
        total=sum(i["qty"] * p.price for i, p in lines),
        currency=next(iter(currencies)) if len(currencies) == 1 else None,
    )
    if needs_address:
        order.email = form["email"][:120]
        order.country_code = form["country"]
        order.address = form["address"][:200]
        order.zip_code = form["zip"][:20]
    elif EMAIL_RE.match(form["email"]):
        order.email = form["email"][:120]
    for i, p in lines:
        order.items.append(OrderItem(
            product_id=p.id, product_name=p.name, size=i["size"], price=p.price, qty=i["qty"], currency=p.currency,
            printful_variant_id=p.printful_map.get(i["size"]) if p.is_printful else None,
        ))

    if not online:
        # Без Stripe: як раніше — замовлення без оплати на сайті
        db.session.add(order)
        db.session.commit()
        session["cart"] = []
        return jsonify({"message": f"Замовлення №{order.id} прийнято. Ми зв'яжемося для підтвердження.", "order_id": order.id})

    # Зі Stripe: замовлення чекає оплати, покупця відправляємо на сторінку оплати Stripe.
    # Кошик не чистимо: якщо покупець передумає й повернеться, товари лишаться.
    order.status = "pending"
    order.payment_status = "unpaid"
    db.session.add(order)
    db.session.commit()
    try:
        session_id, pay_url = payments.create_checkout(
            order,
            [(f"{p.name} ({i['size']})", p.price, i["qty"]) for i, p in lines],
            success_url=url_for("order_done", order_id=order.id, _external=True) + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=url_for("index", payment="cancelled", _external=True) + "#shop",
        )
    except payments.PaymentError as e:
        order.status, order.payment_status = "cancelled", "failed"
        db.session.commit()
        app.logger.error("Stripe: %s", e)
        return json_error("Не вдалося відкрити оплату. Спробуйте ще раз за хвилину", 502)
    order.stripe_session_id = session_id
    db.session.commit()
    return jsonify({"redirect": pay_url, "order_id": order.id})


@app.get("/order/<int:order_id>/done")
def order_done(order_id):
    """Сюди Stripe повертає покупця після оплати."""
    order = db.session.get(Order, order_id)
    sid = request.args.get("session_id", "")
    if not order or not sid or sid != order.stripe_session_id:
        abort(404)
    if order.payment_status != "paid":
        # Вебхук може прийти на кілька секунд пізніше — перевіряємо оплату в Stripe напряму
        try:
            if payments.get_session_status(sid) == "paid":
                order = fulfillment.mark_paid(order.id)
        except payments.PaymentError as e:
            app.logger.error("Stripe: %s", e)
    if order.payment_status == "paid":
        session["cart"] = []
    return render_template("order_done.html", order=order, cart_count=sum(i["qty"] for i, _ in cart_lines()))


@app.post("/stripe/webhook")
def stripe_webhook():
    """Stripe повідомляє про оплату сюди. Адресу треба додати в Stripe → Developers → Webhooks."""
    try:
        event = payments.parse_webhook(request.get_data(), request.headers.get("Stripe-Signature"))
    except payments.PaymentError as e:
        app.logger.warning("Stripe webhook відхилено: %s", e)
        return "bad signature", 400
    obj = event.get("data", {}).get("object", {})
    order_id = (obj.get("metadata") or {}).get("order_id") or obj.get("client_reference_id")
    if not order_id or not str(order_id).isdigit():
        return "ok"
    order = db.session.get(Order, int(order_id))
    if order is None or order.stripe_session_id != obj.get("id"):
        return "ok"
    kind = event.get("type")
    if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded") \
            and obj.get("payment_status") == "paid":
        fulfillment.mark_paid(order.id)
    elif kind in ("checkout.session.expired", "checkout.session.async_payment_failed"):
        fulfillment.mark_expired(order.id)
    return "ok"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=not os.environ.get("RENDER"))
