# LIZKA — магазин одягу (Python 3 + Flask + PostgreSQL)

## Локальний запуск (Windows, PowerShell)
```
cd D:\rabota2281337krutostdengisuki\lizkasuchka228
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py
```
- Сайт: http://127.0.0.1:5000
- Адмінка: http://127.0.0.1:5000/admin (локально пароль `admin`)

Локально база — SQLite-файл `instance/lizka.db`, створюється сам разом зі стартовими товарами.
Щоб почати з чистої бази, видали папку `instance`.

## Деплой на Render
Через **New → Blueprint** (кнопка New у правому верхньому куті дашборду):
Render прочитає `render.yaml` і створить:
- веб-сервіс `lizka` (Flask + Gunicorn)
- базу PostgreSQL `lizka-db` і сам підставить її адресу в `DATABASE_URL`
- випадковий `SECRET_KEY`

При створенні Render попросить ввести `ADMIN_PASSWORD` — це пароль від адмінки.

Після цього кожен `git push` у `main` перевикладає сайт.

## Структура
- `app.py` — вітрина, кошик, оформлення замовлення
- `admin.py` — адмінка: замовлення (зміна статусу) і товари (додати/редагувати/сховати)
- `models.py` — таблиці БД: Product, Order, OrderItem
- `products.py` — категорії, стартові товари, хелпери
- `templates/` — шаблони сайту, `templates/admin/` — шаблони адмінки
- `static/` — CSS і JS

## API вітрини
Усі POST-запити потребують заголовок `X-CSRF-Token` (береться з `<meta name="csrf-token">`).
- `GET  /api/products/<id>`
- `GET  /api/cart`
- `POST /api/cart/add` — `{ "id": 1, "size": "M" }`
- `POST /api/cart/update` — `{ "index": 0, "action": "inc" | "dec" | "del" }`
- `POST /api/checkout` — `{ "name", "phone", "city", "branch", "comment" }`
- `GET  /healthz`

## Що далі
- Фото товарів (завантаження з адмінки в хмарне сховище, бо диск Render не зберігається)
- Сповіщення про нові замовлення в Telegram
- Залишки по розмірах
- Міграції БД (Flask-Migrate), коли почнемо змінювати таблиці
