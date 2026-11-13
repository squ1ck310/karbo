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
- `models.py` — таблиці БД: Product, ProductImage, Order, OrderItem
- `images.py` — обробка завантажених фото
- `remote_images.py` — фото за посиланням (Imgur тощо)
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

## Фото товарів
Завантажуються в адмінці на сторінці товару (можна кілька за раз, до 10 на товар).
Кожне фото автоматично повертається за EXIF, зменшується до 1600 px і стискається у WebP,
а потім зберігається прямо в PostgreSQL (таблиця `product_image`), бо диск Render не постійний.
Віддаються за адресою `/img/<id>.webp` з довгим кешуванням.

Також фото можна додати **за посиланням** (поле під завантаженням, по одному на рядок):
- `imgur.com/abc1234` автоматично перетворюється на пряме `https://i.imgur.com/abc1234.jpg`
- підходить будь-яке пряме https-посилання на картинку
- альбоми Imgur і prnt.sc відхиляються з поясненням
- сервер перевіряє, що за посиланням справді картинка (і не пускає запити на внутрішні адреси)

Увага: Imgur з 30.09.2025 заблокований для користувачів з Великої Британії — там такі фото не відображаються.

## Що далі
- Сповіщення про нові замовлення в Telegram
- Залишки по розмірах
- Міграції БД (Flask-Migrate), коли почнемо змінювати таблиці
