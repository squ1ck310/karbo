"""Оплата через Stripe Checkout (сторінка оплати Stripe: картки, Apple Pay, Google Pay).

Змінні середовища:
  STRIPE_SECRET_KEY      — секретний ключ (sk_test_... для тестів, sk_live_... для справжніх оплат)
  STRIPE_WEBHOOK_SECRET  — секрет вебхука (whsec_...), Stripe → Developers → Webhooks
"""

import json
import os

import stripe

# Stripe приймає суму в найменших одиницях (центи, пенси, копійки)


class PaymentError(Exception):
    pass


def is_configured():
    return bool(os.environ.get("STRIPE_SECRET_KEY"))


def _setup():
    key = os.environ.get("STRIPE_SECRET_KEY")
    if not key:
        raise PaymentError("Не задано STRIPE_SECRET_KEY")
    stripe.api_key = key


def create_checkout(order, lines, success_url, cancel_url):
    """Створює сесію оплати Stripe. lines — [(назва, ціна_в_одиницях, к-сть)], валюта — order.currency.
    Повертає (session_id, url сторінки оплати)."""
    currency = order.currency.lower()
    params = {
        "mode": "payment",
        "line_items": [{
            "quantity": qty,
            "price_data": {
                "currency": currency,
                "unit_amount": int(price) * 100,
                "product_data": {"name": name[:250]},
            },
        } for name, price, qty in lines],
        "success_url": success_url,
        "cancel_url": cancel_url,
        # Звʼязок оплати із замовленням на сайті — за ним вебхук знаходить замовлення. Не прибирати.
        "client_reference_id": str(order.id),
        "metadata": {"order_id": str(order.id)},
        # ===== Налаштування з Stripe Checkout Studio (див. STRIPE_INTEGRATION_TODO.md) =====
        # "hosted_page" — назва цього режиму в API 2026-10-28, на якому працює stripe-python 17
        "ui_mode": "hosted_page",
        "billing_address_collection": "auto",
        "phone_number_collection": {"enabled": False},
        "automatic_tax": {"enabled": True},
        "allow_promotion_codes": True,
        # payment_method_collection не передаємо: він лише для mode="subscription"
        "submit_type": "auto",
        "shipping_address_collection": {"allowed_countries": [
            "AD", "AL", "AT", "AX", "BA", "BE", "BG", "BY", "CH", "CZ", "DE", "DK", "EE", "ES",
            "FI", "FO", "FR", "GB", "GG", "GI", "GR", "HR", "HU", "IE", "IM", "IS", "IT", "JE",
            "LI", "LT", "LU", "LV", "MC", "MD", "ME", "MK", "MT", "NL", "NO", "PL", "PT", "RO",
            "RS", "RU", "SE", "SI", "SJ", "SK", "SM", "UA", "VA",
        ]},
        "name_collection": {
            "individual": {"enabled": True},
            "business": {"enabled": True, "optional": True},
        },
        "payment_method_options": {"card": {"restrictions": {"brands_blocked": ["discover_global_network"]}}},
        "saved_payment_method_options": {"payment_method_save": "enabled"},
        "integration_identifier": "hosted_mobile_app_0001",
        "origin_context": "mobile_app",
    }
    try:
        _setup()
        s = stripe.checkout.Session.create(**params)
    except stripe.StripeError as e:
        raise PaymentError(getattr(e, "user_message", None) or str(e)) from None
    return s.id, s.url


def get_session_status(session_id):
    """'paid' | 'unpaid' | 'no_payment_required' — для сторінки «дякуємо», якщо вебхук ще не дійшов."""
    try:
        _setup()
        s = stripe.checkout.Session.retrieve(session_id)
    except stripe.StripeError as e:
        raise PaymentError(str(e)) from None
    return s.payment_status


def parse_webhook(payload: bytes, sig_header: str):
    """Перевіряє підпис Stripe і повертає подію як звичайний dict.
    Без правильного підпису будь-хто міг би «оплатити» замовлення фальшивим запитом."""
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise PaymentError("Не задано STRIPE_WEBHOOK_SECRET")
    try:
        stripe.WebhookSignature.verify_header(payload.decode("utf-8"), sig_header or "", secret, tolerance=300)
    except (stripe.SignatureVerificationError, ValueError) as e:
        raise PaymentError(f"Невірний підпис вебхука: {e}") from None
    return json.loads(payload)
