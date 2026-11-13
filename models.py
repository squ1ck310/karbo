"""Моделі бази даних (SQLAlchemy).
Локально — SQLite-файл instance/lizka.db, на Render — PostgreSQL (DATABASE_URL)."""

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import deferred

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

    images = db.relationship(
        "ProductImage", backref="product", cascade="all, delete-orphan",
        order_by="ProductImage.position, ProductImage.id",
    )

    @property
    def size_list(self):
        return [s.strip() for s in (self.sizes or "").split(",") if s.strip()]

    @property
    def main_image(self):
        """Перше фото — головне (показується в каталозі). None, якщо фото немає."""
        return self.images[0] if self.images else None


class ProductImage(db.Model):
    """Фото товару: або файл у БД (диск Render не постійний), або зовнішнє посилання."""
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id", ondelete="CASCADE"), nullable=False, index=True)
    # deferred — самі байти вантажаться тільки коли їх реально віддаємо, а не при кожному списку товарів
    data = deferred(db.Column(db.LargeBinary, nullable=False, default=b""))  # порожньо для фото за посиланням
    url = db.Column(db.String(500))         # зовнішнє посилання (Imgur тощо); якщо є — data не використовується
    mimetype = db.Column(db.String(30), nullable=False, default="image/webp")
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    size = db.Column(db.Integer)            # байти
    position = db.Column(db.Integer, default=0, nullable=False)


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


def migrate(engine):
    """Мінімальні міграції для вже існуючих баз (create_all не додає колонки в старі таблиці)."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    if "product_image" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("product_image")}
        if "url" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE product_image ADD COLUMN url VARCHAR(500)"))
