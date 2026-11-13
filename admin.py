"""Адмінка: /admin. Вхід за паролем зі змінної середовища ADMIN_PASSWORD."""

import hmac
import os
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for

from models import ORDER_STATUSES, Order, OrderItem, Product, db
from products import CATEGORIES, CATEGORY_IDS, CATEGORY_NAMES, SHAPES

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
    return {"CATEGORY_NAMES": CATEGORY_NAMES, "ORDER_STATUSES": ORDER_STATUSES}


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
    return render_template("admin/orders.html", orders=query.limit(200).all(), active_status=status)


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
    p.sizes = ",".join(s.strip() for s in form.get("sizes", "").split(",") if s.strip())
    p.badge = form.get("badge", "").strip()[:30]
    p.shape = form.get("shape", "tee")
    p.color = form.get("color", "#FFFFFF")
    p.bg = form.get("bg", "#ECE6F5")
    p.is_active = form.get("is_active") == "on"
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
            db.session.commit()
            flash(f"Товар «{p.name}» збережено")
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
