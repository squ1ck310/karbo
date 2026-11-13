# LIZKA — магазин одягу (Python 3 + Flask)

## Запуск (Windows)
```
cd D:\rabota2281337krutostdengisuki\lizkasuchka228
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
Відкрий http://127.0.0.1:5000

## Структура
- `app.py` — сервер Flask: сторінки та API кошика
- `products.py` — товари, категорії, силуети одягу (поки замість фото)
- `templates/` — HTML-шаблони Jinja (`base.html` — каркас, `index.html` — головна)
- `static/css/styles.css` — стилі
- `static/js/main.js` — модалка товару й кошик (працює через API)

## API
- `GET  /api/products/<id>` — товар
- `GET  /api/cart` — кошик
- `POST /api/cart/add` — `{ "id": 1, "size": "M" }`
- `POST /api/cart/update` — `{ "index": 0, "action": "inc" | "dec" | "del" }`
- `POST /api/checkout` — заглушка

Кошик зберігається в сесії Flask (cookie).

## Що далі
- База даних (SQLite + SQLAlchemy) замість списку в `products.py`
- Фото товарів у `static/img/`
- Форма оформлення замовлення
- Адмінка для товарів
