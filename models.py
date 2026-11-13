"""Моделі бази даних (SQLAlchemy).
Локально — SQLite-файл instance/lizka.db, на Render — PostgreSQL (DATABASE_URL)."""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

ORDER_STATUSES = {
    "new": "Нове",
    "confirmed": "Підтверджене",
    "shipped": "Відправлене",
    "done": "Виконане",
    "cancelled": "Скасоване",
}


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(30), nullable=False, index=True)
    price = db.Column(db.Integer, nullable=False)          # у гривнях
    desc = db.Column(db.Text, default="")
    sizes = db.Column(db.String(200), default="")         # "XS,S,M,L"
    badge = db.Column(db.String(30), default="")
    # Поки замість фото — силует (shape) і кольори
    shape = db.Column(db.String(20), default="tee")
    color = db.Column(db.String(9), default="#FFFFFF")
    bg = db.Column(db.String(9), default="#ECE6F5")
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    @property
    def size_list(self):
        return [s.strip() for s in (self.sizes or "").split(",") if s.strip()]


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    customer_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    np_branch = db.Column(db.String(120), nullable=False)  # відділення Нової Пошти
    comment = db.Column(db.Text, default="")
    total = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="new", nullable=False, index=True)

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy="joined")

    @property
    def status_name(self):
        return ORDER_STATUSES.get(self.status, self.status)


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    # Назву й ціну копіюємо, щоб замовлення не змінювалось, якщо товар потім відредагують
    product_name = db.Column(db.String(120), nullable=False)
    size = db.Column(db.String(10), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    qty = db.Column(db.Integer, nullable=False)
