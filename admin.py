"""Адмінка: /admin. Вхід за паролем зі змінної середовища ADMIN_PASSWORD."""

import hmac
import json
import os
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from images import ImageError, process_image
from remote_images import RemoteImageError, inspect_remote_image, normalize_url
from models import ORDER_STATUSES, Order, OrderItem, Product, ProductImage, db
from products import CATEGORIES, CATEGORY_IDS, CATEGORY_NAMES, CURRENCIES, SHAPES
import printful
import fulfillment
import payments

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def admin_password():
    # Локально можна без змінної — тоді пароль "admin". На Render його ОБОВ'ЯЗКОВО треба задати.
    if os.environ.get("RENDER"):
        return os.environ.get("ADMIN_PASSWORD")
    return os.environ.get("ADMIN_PASSWORD", "admin")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


@admin_bp.app_context_processor
def admin_globals():
    return {"CATEGORY_NAMES": CATEGORY_NAMES, "ORDER_STATUSES": ORDER_STATUSES,
            "printful_ready": printful.is_configured(), "stripe_ready": payments.is_configured()}


# ===== Вхід / вихід =====
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        expected = admin_password()
        given = request.form.get("password", "")
        if expected and hmac.compare_digest(given.encode(), expected.encode()):
            session["is_admin"] = True
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/admin") else url_for("admin.orders"))
        flash("Невірний пароль" if expected else "ADMIN_PASSWORD не задано на сервері")
    return render_template("admin/login.html")


@admin_bp.post("/logout")
def logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin.login"))


# ===== Замовлення =====
@admin_bp.get("/")
@login_required
def orders():
    status = request.args.get("status", "")
    query = Order.query.order_by(Order.created_at.desc())
    if status in ORDER_STATUSES:
        query = query.filter_by(status=status)
    cancelled_count = Order.query.filter_by(status="cancelled").count()
    return render_template("admin/orders.html", orders=query.limit(200).all(), active_status=status,
                           cancelled_count=cancelled_count)


@admin_bp.post("/orders/purge-cancelled")
@login_required
def purge_cancelled():
    ids = db.session.query(Order.id).filter_by(status="cancelled")
    OrderItem.query.filter(OrderItem.order_id.in_(ids.scalar_subquery())).delete(synchronize_session=False)
    deleted = Order.query.filter_by(status="cancelled").delete(synchronize_session=False)
    db.session.commit()
    flash(f"Видалено скасованих замовлень: {deleted}" if deleted else "Скасованих замовлень немає")
    return redirect(url_for("admin.orders", status="cancelled"))


@admin_bp.post("/orders/<int:order_id>/status")
@login_required
def order_status(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    new_status = request.form.get("status")
    if new_status in ORDER_STATUSES:
        order.status = new_status
        db.session.commit()
        flash(f"Замовлення №{order.id}: статус «{order.status_name}»")
    return redirect(request.referrer or url_for("admin.orders"))


# ===== Товари =====
@admin_bp.get("/products")
@login_required
def products():
    return render_template("admin/products.html", products=Product.query.order_by(Product.id).all())


def fill_product(p, form):
    """Заповнює товар з форми. Повертає список помилок."""
    errors = []
    p.name = form.get("name", "").strip()[:120]
    p.category = form.get("category", "")
    p.desc = form.get("desc", "").strip()
    if not p.is_printful:   # розміри товарів Printful беруться з Printful, руками їх не міняємо
        p.sizes = ",".join(s.strip() for s in form.get("sizes", "").split(",") if s.strip())
    p.badge = form.get("badge", "").strip()[:30]
    p.shape = form.get("shape", "tee")
    p.color = form.get("color", "#FFFFFF")
    p.bg = form.get("bg", "#ECE6F5")
    p.is_active = form.get("is_active") == "on"
    p.currency = form.get("currency", "UAH")
    if p.currency not in CURRENCIES:
        errors.append("Оберіть валюту")
    try:
        p.price = int(form.get("price", ""))
        if p.price <= 0:
            raise ValueError
    except ValueError:
        errors.append("Ціна має бути цілим числом більше нуля")
    if not p.name:
        errors.append("Вкажіть назву")
    if p.category not in CATEGORY_IDS:
        errors.append("Оберіть категорію")
    if p.shape not in SHAPES:
        errors.append("Оберіть силует")
    if not p.sizes:
        errors.append("Вкажіть хоча б один розмір")
    return errors


MAX_PHOTOS = 10


def add_photos(p, files):
    """Обробляє завантажені фото й додає до товару. Повертає кількість доданих."""
    files = [f for f in files if f and f.filename]
    free = MAX_PHOTOS - len(p.images)
    if len(files) > free:
        flash(f"Можна мати до {MAX_PHOTOS} фото на товар. Зайві файли пропущено")
        files = files[:max(free, 0)]
    next_pos = max((img.position for img in p.images), default=-1) + 1
    added = 0
    for f in files:
        try:
            data, w, h = process_image(f)
        except ImageError as e:
            flash(str(e))
            continue
        p.images.append(ProductImage(data=data, width=w, height=h, size=len(data), position=next_pos))
        next_pos += 1
        added += 1
    return added


def add_photo_urls(p, text):
    """Додає фото за посиланнями (по одному на рядок). Повертає кількість доданих."""
    links = [line.strip() for line in text.splitlines() if line.strip()]
    if not links:
        return 0
    free = MAX_PHOTOS - len(p.images)
    if len(links) > free:
        flash(f"Можна мати до {MAX_PHOTOS} фото на товар. Зайві посилання пропущено")
        links = links[:max(free, 0)]
    next_pos = max((img.position for img in p.images), default=-1) + 1
    added = 0
    for link in links:
        try:
            url = normalize_url(link)
            w, h = inspect_remote_image(url)
        except RemoteImageError as e:
            flash(f"{link[:60]}: {e}")
            continue
        if w is None:
            flash(f"{link[:60]}: сайт не дав серверу перевірити фото. Його додано, але переконайся, що воно відкривається")
        p.images.append(ProductImage(url=url, width=w, height=h, size=0, position=next_pos))
        next_pos += 1
        added += 1
    return added


@admin_bp.route("/products/new", methods=["GET", "POST"])
@admin_bp.route("/products/<int:product_id>", methods=["GET", "POST"])
@login_required
def product_form(product_id=None):
    p = db.session.get(Product, product_id) if product_id else Product(is_active=True, shape="tee", color="#FFFFFF", bg="#ECE6F5")
    if p is None:
        abort(404)
    if request.method == "POST":
        errors = fill_product(p, request.form)
        if errors:
            for e in errors:
                flash(e)
        else:
            db.session.add(p)
            added = add_photos(p, request.files.getlist("photos"))
            added += add_photo_urls(p, request.form.get("photo_urls", ""))
            db.session.commit()
            flash(f"Товар «{p.name}» збережено" + (f", додано фото: {added}" if added else ""))
            # Після додавання фото лишаємось на сторінці товару, щоб їх одразу побачити
            if any(f.filename for f in request.files.getlist("photos")) or request.form.get("photo_urls", "").strip():
                return redirect(url_for("admin.product_form", product_id=p.id))
            return redirect(url_for("admin.products"))
    categories = [c for c in CATEGORIES if c["id"] != "all"]
    return render_template("admin/product_form.html", p=p, categories=categories, shapes=SHAPES)


@admin_bp.post("/products/<int:product_id>/delete")
@login_required
def product_delete(product_id):
    p = db.session.get(Product, product_id) or abort(404)
    name = p.name
    # У старих замовленнях назва й ціна товару вже збережені копією,
    # тому просто відвʼязуємо їх від товару, а не видаляємо
    OrderItem.query.filter_by(product_id=p.id).update({"product_id": None})
    db.session.delete(p)
    db.session.commit()
    flash(f"Товар «{name}» видалено")
    return redirect(url_for("admin.products"))


# ===== Фото товару =====
def get_image(product_id, image_id):
    img = db.session.get(ProductImage, image_id)
    if not img or img.product_id != product_id:
        abort(404)
    return img


@admin_bp.post("/products/<int:product_id>/images/<int:image_id>/delete")
@login_required
def image_delete(product_id, image_id):
    db.session.delete(get_image(product_id, image_id))
    db.session.commit()
    flash("Фото видалено")
    return redirect(url_for("admin.product_form", product_id=product_id))


@admin_bp.post("/products/<int:product_id>/images/<int:image_id>/main")
@login_required
def image_make_main(product_id, image_id):
    img = get_image(product_id, image_id)
    img.position = min(i.position for i in img.product.images) - 1
    db.session.commit()
    flash("Головне фото змінено")
    return redirect(url_for("admin.product_form", product_id=product_id))


# ===== Printful =====
@admin_bp.post("/printful/sync")
@login_required
def printful_sync():
    """Підтягує товари з магазину Printful. Нові товари створюються прихованими,
    щоб ти перевірив ціну в гривнях перед показом на сайті."""
    try:
        items = [i for i in printful.list_sync_products() if not i.get("is_ignored")]
        current_ids = {i["id"] for i in items}
        created = updated = relinked = 0
        seen, matched = set(), set()
        for item in items:
            data = printful.parse_product(printful.get_sync_product(item["id"]))
            if not data["variants"]:
                continue
            seen.add(data["id"])
            p = Product.query.filter_by(printful_id=data["id"]).first()
            if p is None and data.get("external_id"):
                p = Product.query.filter_by(printful_external_id=data["external_id"]).first()
            if p is None:
                # Товар у Printful перестворили (новий ID) — знаходимо старий товар сайту за назвою,
                # щоб не плодити дубль і не губити ціну, фото та старі замовлення
                stale = Product.query.filter(
                    Product.fulfillment == "printful",
                    db.or_(Product.printful_id.is_(None), Product.printful_id.notin_(current_ids)),
                ).all()
                want = fulfillment.norm_name(data["name"])
                p = next((c for c in stale if c.id not in matched and want in
                          {fulfillment.norm_name(c.printful_name), fulfillment.norm_name(c.name)}), None)
                if p is not None:
                    relinked += 1
            elif p.printful_id == data["id"]:
                updated += 1
            else:
                relinked += 1
            if p is None:
                p = Product(
                    name=data["name"][:120], category=data["category"], shape=data["shape"],
                    color="#FFFFFF", bg="#ECE6F5", desc="", badge="", is_active=False,
                    # Ціну й валюту беремо з Printful, якщо валюта з нашого списку
                    price=round(data["price"]) if data["currency"] in CURRENCIES else 0,
                    currency=data["currency"] if data["currency"] in CURRENCIES else "UAH",
                    fulfillment="printful", printful_id=data["id"],
                )
                db.session.add(p)
                for pos, url in enumerate(data["previews"] or [data["thumbnail"]]):
                    if url:
                        p.images.append(ProductImage(url=url, size=0, position=pos))
                created += 1
            # Привʼязку, розміри й ID варіантів оновлюємо завжди; назву, ціну, опис — не чіпаємо
            fulfillment.apply_printful_data(p, data)
            db.session.flush()
            matched.add(p.id)
        # Товари, яких у Printful більше немає, ховаємо з сайту
        gone = Product.query.filter(Product.fulfillment == "printful", Product.is_active.is_(True))
        if seen:
            gone = gone.filter(Product.printful_id.notin_(seen))
        hidden = gone.update({"is_active": False}, synchronize_session=False)
        db.session.commit()
    except printful.PrintfulError as e:
        db.session.rollback()
        flash(str(e))
        return redirect(url_for("admin.products"))
    msg = f"Синхронізовано з Printful: нових {created}, оновлено {updated}"
    if relinked:
        msg += f", заново привʼязано (змінився ID у Printful) {relinked}"
    if hidden:
        msg += f", приховано (зникли з Printful) {hidden}"
    flash(msg)
    if created:
        flash("Нові товари поки приховані: перевір ціну й валюту і постав галочку «Показувати на сайті»")
    return redirect(url_for("admin.products"))


@admin_bp.post("/orders/<int:order_id>/printful")
@login_required
def order_to_printful(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    if order.payment_status in ("unpaid", "expired", "failed"):
        # Захист: Printful спише гроші з тебе, а покупець ще не заплатив
        flash(f"Замовлення №{order.id} не оплачене, у Printful його не відправляю")
    else:
        flash(fulfillment.send_to_printful(order, confirm=False))
        db.session.commit()
    return redirect(request.referrer or url_for("admin.orders"))


@admin_bp.post("/orders/<int:order_id>/printful/confirm")
@login_required
def order_printful_confirm(order_id):
    """Підтверджує чернетку в Printful прямо з адмінки: замовлення йде в друк."""
    order = db.session.get(Order, order_id) or abort(404)
    if not order.printful_order_id:
        flash("Спершу створи чернетку в Printful")
    elif order.payment_status in ("unpaid", "expired", "failed"):
        flash(f"Замовлення №{order.id} не оплачене, підтверджувати не можна")
    else:
        try:
            result = printful.confirm_order(order.printful_order_id)
            order.printful_status = result.get("status", "pending")
            order.printful_error = None
            flash(f"Замовлення №{order.id} пішло в друк. Printful списав оплату з твого Wallet")
        except printful.PrintfulError as e:
            order.printful_error = str(e)[:300]
            flash(f"Не вдалося підтвердити: {e}")
        db.session.commit()
    return redirect(request.referrer or url_for("admin.orders"))


@admin_bp.post("/orders/<int:order_id>/printful/refresh")
@login_required
def order_printful_refresh(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    try:
        result = printful.get_order(f"lizka-{order.id}")
        order.printful_order_id = result.get("id")
        order.printful_status = result.get("status")
        shipments = result.get("shipments") or []
        tracks = [s.get("tracking_number") for s in shipments if s.get("tracking_number")]
        if tracks and order.status in ("new", "confirmed"):
            order.status = "shipped"
        db.session.commit()
        flash(f"Printful: статус «{order.printful_status}»" + (f", трек: {', '.join(tracks)}" if tracks else ""))
    except printful.PrintfulError as e:
        flash(str(e))
    return redirect(request.referrer or url_for("admin.orders"))
