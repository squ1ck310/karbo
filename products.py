"""Категорії, стартові товари (заливаються в порожню базу) і хелпери для шаблонів."""

from markupsafe import Markup, escape

CATEGORIES = [
    {"id": "all", "name": "Усе"},
    {"id": "tees", "name": "Футболки"},
    {"id": "hoodies", "name": "Худі"},
    {"id": "pants", "name": "Штани"},
    {"id": "dresses", "name": "Сукні"},
    {"id": "outer", "name": "Верхній одяг"},
]

SEED_PRODUCTS = [
    {"id": 1, "name": "Футболка оверсайз", "category": "tees", "price": 690, "shape": "tee",
     "color": "#F7F4FB", "bg": "#E4DCEF", "sizes": ["XS", "S", "M", "L", "XL"], "badge": "Хіт",
     "desc": "Щільна бавовна 220 г/м², вільний крій, не сідає після прання."},
    {"id": 2, "name": "Футболка рожева", "category": "tees", "price": 690, "shape": "tee",
     "color": "#E0559A", "bg": "#F6D3E4", "sizes": ["XS", "S", "M", "L"],
     "desc": "Та сама оверсайз модель у кольорі фуксії."},
    {"id": 3, "name": "Худі з начосом", "category": "hoodies", "price": 1490, "shape": "hoodie",
     "color": "#231942", "bg": "#C9BEDF", "sizes": ["S", "M", "L", "XL"], "badge": "Новинка",
     "desc": "Тринитка з начосом, капюшон на подвійній тканині, кишеня-кенгуру."},
    {"id": 4, "name": "Худі лавандове", "category": "hoodies", "price": 1490, "shape": "hoodie",
     "color": "#B9A6D6", "bg": "#ECE6F5", "sizes": ["XS", "S", "M", "L"],
     "desc": "М'яке худі на щодень, трохи вкорочене."},
    {"id": 5, "name": "Джинси прямі", "category": "pants", "price": 1290, "shape": "pants",
     "color": "#4A5FA8", "bg": "#D5DCF0", "sizes": ["25", "26", "27", "28", "29", "30"],
     "desc": "Висока посадка, прямий крій, щільний деним без еластану."},
    {"id": 6, "name": "Карго штани", "category": "pants", "price": 1190, "shape": "pants",
     "color": "#6B6485", "bg": "#DEDAE6", "sizes": ["S", "M", "L"],
     "desc": "Широкі штани з накладними кишенями та затяжками внизу."},
    {"id": 7, "name": "Сукня міді", "category": "dresses", "price": 1690, "shape": "dress",
     "color": "#231942", "bg": "#D9D0EA", "sizes": ["XS", "S", "M", "L"], "badge": "Новинка",
     "desc": "Віскоза, приталений верх, довжина нижче коліна."},
    {"id": 8, "name": "Сукня-сорочка", "category": "dresses", "price": 1590, "shape": "dress",
     "color": "#F2B5CF", "bg": "#FBE6EF", "sizes": ["S", "M", "L"],
     "desc": "Легка сукня на ґудзиках, можна носити з поясом."},
    {"id": 9, "name": "Куртка бомбер", "category": "outer", "price": 2390, "shape": "jacket",
     "color": "#3B2F63", "bg": "#CFC6E2", "sizes": ["S", "M", "L", "XL"],
     "desc": "Нейлон, утеплювач 100 г, підходить на осінь."},
    {"id": 10, "name": "Жакет оверсайз", "category": "outer", "price": 2190, "shape": "jacket",
     "color": "#E8E2D9", "bg": "#EFEAF4", "sizes": ["XS", "S", "M"],
     "desc": "Вільний жакет з підплечниками, вовна з поліестером."},
]

CATEGORY_IDS = {c["id"] for c in CATEGORIES if c["id"] != "all"}
CATEGORY_NAMES = {c["id"]: c["name"] for c in CATEGORIES}
SHAPES = {"tee": "Футболка", "hoodie": "Худі", "pants": "Штани", "dress": "Сукня", "jacket": "Куртка"}


def format_price(value: int) -> str:
    return f"{value:,}".replace(",", " ") + " ₴"


def garment_svg(shape: str, color: str) -> Markup:
    """Силует одягу замість фото. Коли будуть фото — заміни на <img>."""
    stroke = "#231942"
    s = f'fill="{color}" stroke="{stroke}" stroke-width="3" stroke-linejoin="round"'
    line = f'fill="none" stroke="{stroke}" stroke-width="3"'
    shapes = {
        "tee": f'<path {s} d="M70 20 L40 32 L12 62 L32 80 L45 68 L45 170 L155 170 L155 68 L168 80 L188 62 L160 32 L130 20 Q100 44 70 20 Z"/>',
        "hoodie": f'<path {s} d="M70 26 L38 38 L14 120 L36 126 L48 82 L48 172 L152 172 L152 82 L164 126 L186 120 L162 38 L130 26 Q138 4 100 4 Q62 4 70 26 Z"/>'
                  f'<path {line} d="M70 26 Q100 52 130 26"/><path {line} d="M72 118 L128 118 L136 150 L64 150 Z"/>',
        "pants": f'<path {s} d="M56 10 L144 10 L156 176 L114 176 L100 70 L86 176 L44 176 Z"/><path {line} d="M56 26 L144 26"/>',
        "dress": f'<path {s} d="M76 8 L82 40 Q100 52 118 40 L124 8 L136 14 L128 70 L170 176 L30 176 L72 70 L64 14 Z"/><path {line} d="M72 70 L128 70"/>',
        "jacket": f'<path {s} d="M70 18 L36 30 L14 140 L38 146 L48 74 L48 172 L152 172 L152 74 L162 146 L186 140 L164 30 L130 18 L100 56 Z"/>'
                  f'<path {line} d="M100 56 L100 172 M70 18 L84 70 L100 56 M130 18 L116 70 L100 56"/>',
    }
    body = shapes.get(shape, shapes["tee"])
    return Markup(f'<svg viewBox="0 0 200 180" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">{body}</svg>')


def image_url(image):
    if image.url:
        return image.url
    from flask import url_for
    return url_for("product_image", image_id=image.id)


def product_media(p, lazy=True):
    """Головне фото товару, а якщо фото немає — силует."""
    img = p.main_image
    if not img:
        return garment_svg(p.shape, p.color)
    loading = ' loading="lazy"' if lazy else ""
    size = f' width="{img.width}" height="{img.height}"' if img.width and img.height else ""
    return Markup(
        f'<img src="{escape(image_url(img))}" alt="{escape(p.name)}"{size}{loading} referrerpolicy="no-referrer">'
    )
