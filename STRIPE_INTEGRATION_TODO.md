# Stripe Checkout — що лишилось зробити

Сайт уже створював сесію оплати Stripe (`stripe.checkout.Session.create` у [payments.py](payments.py)),
тому налаштування з Checkout Studio внесено **лише в параметри цього виклику**. Решту коду не змінено.

## Values to Replace

Плейсхолдерів у коді немає. Параметри, які Checkout Studio позначає як «приклад», на сайті вже мають справжні значення.

**Файли з цими параметрами:**
- [payments.py](payments.py), значення передаються з [app.py](app.py) (`api_checkout`)

| Field | Current Value | What to Set |
|-------|--------------|-------------|
| mode | `payment` | Нічого: разова оплата, підписок немає. |
| success_url | `https://<сайт>/order/<id>/done?session_id={CHECKOUT_SESSION_ID}` | Нічого: адреса будується автоматично з домену сайту. |
| cancel_url | `https://<сайт>/?payment=cancelled#shop` | Нічого. |
| line_items | `price_data` з кошика: назва + розмір, ціна, кількість | Нічого. Price ID зі Stripe не потрібні: ціни беруться з адмінки сайту. |

## Configured Parameters

Ці параметри задані в Checkout Studio і вже стоять у коді.

**Файли з цими параметрами:**
- [payments.py](payments.py)

| Parameter | Value |
|-----------|-------|
| ui_mode | `hosted_page` |
| billing_address_collection | `auto` |
| phone_number_collection | `{"enabled": false}` |
| automatic_tax | `{"enabled": true}` |
| allow_promotion_codes | `true` |
| submit_type | `auto` |
| shipping_address_collection.allowed_countries | AD, AL, AT, AX, BA, BE, BG, BY, CH, CZ, DE, DK, EE, ES, FI, FO, FR, GB, GG, GI, GR, HR, HU, IE, IM, IS, IT, JE, LI, LT, LU, LV, MC, MD, ME, MK, MT, NL, NO, PL, PT, RO, RS, RU, SE, SI, SJ, SK, SM, UA, VA (51) |
| name_collection | individual: увімкнено; business: увімкнено, необовʼязково |
| payment_method_options.card.restrictions.brands_blocked | `["discover_global_network"]` |
| saved_payment_method_options.payment_method_save | `enabled` |
| integration_identifier | `hosted_mobile_app_0001` |
| origin_context | `mobile_app` |

### Що свідомо НЕ змінено

| Параметр | Чому |
|----------|------|
| `payment_method_collection: always` | Не передається: Stripe дозволяє його лише для `mode=subscription`, а в нас `payment`. |
| `adjustable_quantity` (є в прикладі Node.js зі Studio) | Не додано: якщо покупець змінить кількість на сторінці Stripe, у замовленні на сайті й у Printful лишиться стара кількість. Кількість міняється в кошику сайту. |
| `client_reference_id`, `metadata.order_id` | Лишились, хоча їх немає в Studio: за ними вебхук знаходить, яке замовлення оплачене. Без них оплати не позначались би. |
| `customer_email`, `expires_at`, `payment_intent_data` | Прибрано, бо їх немає в Studio. Наслідок: email покупець вводить на сторінці Stripe, а неоплачена сесія тепер живе 24 години (було 1 година), після чого замовлення скасовується. |

`ui_mode`: інструкція Studio каже `hosted` для SDK нижче 21.0.0, але найновіший stripe-python на PyPI — 17.0.0,
і він працює з API `2026-10-28.endive`, де цей режим називається `hosted_page`. Версію API в коді не задано,
її бере SDK. Тому в [requirements.txt](requirements.txt) закріплено `stripe>=17,<18`. При переході на 18+ перевір назву режиму.

## Setup and next steps

### 1. Ключі (Render → сервіс → Environment)

| Змінна | Де взяти |
|--------|----------|
| `STRIPE_SECRET_KEY` | Stripe → Developers → API keys → Secret key (`sk_test_...` для тестів, `sk_live_...` для справжніх оплат) |
| `STRIPE_WEBHOOK_SECRET` | Stripe → Developers → Webhooks → твій endpoint → Signing secret (`whsec_...`) |
| `PRINTFUL_AUTO_CONFIRM` | Необовʼязково. `1` — оплачені замовлення одразу йдуть у друк. Без неї в Printful створюється чернетка, яку підтверджуєш в адмінці. |

Ключі не пиши в код і не коміть у Git. **Тестовий секретний ключ уже потрапив у чат — перевипусти його:**
Developers → API keys → Secret key → ⋯ → Roll key, і новий постав у Render.

Локально (PowerShell): `$env:STRIPE_SECRET_KEY="sk_test_..."; python app.py`

### 2. Stripe Tax — обовʼязково, бо `automatic_tax` увімкнено

Без цього Stripe може відмовитись створювати сторінку оплати, і покупець побачить «Не вдалося відкрити оплату».
1. Stripe → Settings → Tax → активуй Stripe Tax, вкажи адресу бізнесу (UK).
2. Там же вибери податковий код за замовчуванням для одягу і **поведінку податку за замовчуванням**:
   `inclusive` — ПДВ уже в ціні (звично для покупців у UK/ЄС), `exclusive` — додається зверху.
3. Tax → Registrations: додай країни, де ти зареєстрований платником податку. Stripe рахує податок лише там.
   Які реєстрації потрібні тобі, уточни з бухгалтером.

### 3. Вебхук

Stripe → Developers → Webhooks → Add endpoint:
- URL: `https://<твій-сайт>.onrender.com/stripe/webhook`
- події: `checkout.session.completed`, `checkout.session.async_payment_succeeded`,
  `checkout.session.async_payment_failed`, `checkout.session.expired`

### 4. Тест

Картки тестового режиму (будь-яка майбутня дата, будь-який CVC):
- `4242 4242 4242 4242` — успішна оплата
- `4000 0025 0000 3155` — з підтвердженням 3D Secure
- `4000 0000 0000 0002` — відмова

Після оплати замовлення в адмінці має стати «Оплачено», а речі з Printful — зʼявитись у Printful.

### Як це працює

1. Покупець заповнює форму в кошику → замовлення «Очікує оплати» → редірект на сторінку оплати Stripe.
2. Stripe надсилає вебхук → сайт перевіряє підпис → замовлення «Оплачено», статус «Підтверджене».
   Сторінка `/order/<id>/done` додатково питає Stripe, якщо вебхук запізнився. Подвійної обробки не буде.
3. Товари Printful автоматично відправляються в Printful (чернетка або одразу в друк).
4. Неоплачена сесія через 24 години → замовлення «Скасоване».

### Що варто переглянути в Checkout Studio

- **`origin_context: mobile_app`** — сайт відкривається в браузері, а не в мобільному застосунку. Для сайту підходить `web`.
- **RU і BY у списку країн доставки** — Printful туди не доставляє, тож оплачене замовлення не буде виконане.
  Також перевір обмеження для продажу в ці країни з UK. Раджу прибрати.
- **У списку немає US і CA**, а форма на сайті їх пропонує: покупець із США не зможе оплатити.
- **Адресу питають двічі** — у формі сайту і на сторінці Stripe (`shipping_address_collection`).
  Printful зараз отримує адресу з форми сайту, а податок рахується за адресою зі Stripe.
  Якщо адреси різні, вийде розбіжність. Варіант: брати адресу зі Stripe і прибрати поля адреси з форми.
- **`payment_method_save: enabled`** — якщо Stripe відповість помилкою про customer, потрібно додати
  `customer_creation: "always"` (цього параметра немає в Studio, тому його не додано).

### Наступні кроки

- Вартість доставки Printful у сесії оплати (зараз доставку не платить покупець).
- Вебхуки Printful: статус і трек-номер без кнопки «Оновити статус».
- Перевірка, чи Printful доставляє в країну/регіон покупця, до оплати.

### Ресурси

- https://support.stripe.com
- https://docs.stripe.com/mcp
