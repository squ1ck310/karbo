"""Моделі бази даних (SQLAlchemy).
Локально — SQLite-файл instance/lizka.db, на Render — PostgreSQL (DATABASE_URL)."""

import json
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
    # Printful: "own" — свій склад, "printful" — друкує й відправляє Printful
    fulfillment = db.Column(db.String(10), default="own", nullable=False, server_default="own")
    printful_id = db.Column(db.Integer, unique=True)          # id товару в магазині Printful (sync product)
    printful_variants = db.Column(db.Text)                    # JSON {"M": sync_variant_id, ...}
    printful_currency = db.Column(db.String(3))

    images = db.relationship(
        "ProductImage", backref="product", cascade="all, delete-orphan",
        order_by="ProductImage.position, ProductImage.id",
    )

    @property
    def size_list(self):
        return [s.strip() for s in (self.sizes or "").split(",") if s.strip()]

    @property
    def is_printful(self):
        return self.fulfillment == "printful"

    @property
    def printful_map(self):
        try:
            return json.loads(self.printful_variants or "{}")
        except ValueError:
            return {}

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
    # Повна адреса — потрібна для товарів Printful (вони їдуть не Новою Поштою)
    email = db.Column(db.String(120))
    country_code = db.Column(db.String(2))
    address = db.Column(db.String(200))
    zip_code = db.Column(db.String(20))
    printful_order_id = db.Column(db.Integer)
    printful_status = db.Column(db.String(30))
    printful_error = db.Column(db.String(300))

    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy="joined")

    @property
    def status_name(self):
        return ORDER_STATUSES.get(self.status, self.status)

    @property
    def printful_items(self):
        return [i for i in self.items if i.printful_variant_id]


class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    # Назву й ціну копіюємо, щоб замовлення не змінювалось, якщо товар потім відредагують
    product_name = db.Column(db.String(120), nullable=False)
    size = db.Column(db.String(40), nullable=False)          # "M" або "Black / M"
    price = db.Column(db.Integer, nullable=False)
    qty = db.Column(db.Integer, nullable=False)
    printful_variant_id = db.Column(db.BigInteger)            # sync_variant_id, якщо товар з Printful


def migrate(engine):
    """Додає в уже існуючі таблиці колонки, яких там ще немає (create_all цього не робить).
    Нові колонки мають бути nullable або з server_default."""
    from sqlalchemy import inspect, text
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as conn:
        for table in db.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(col.name)} {col.type.compile(dialect=engine.dialect)}"
                if col.server_default is not None:
                    ddl += f" DEFAULT '{col.server_default.arg}' NOT NULL"
                conn.execute(text(ddl))
        # Розширення колонок: PostgreSQL суворо перевіряє довжину рядка (SQLite — ні)
        if engine.dialect.name == "postgresql" and "order_item" in existing_tables:
            size_col = next(c for c in insp.get_columns("order_item") if c["name"] == "size")
            if getattr(size_col["type"], "length", None) and size_col["type"].length < 40:
                conn.execute(text("ALTER TABLE order_item ALTER COLUMN size TYPE VARCHAR(40)"))
