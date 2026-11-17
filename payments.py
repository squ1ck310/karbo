"""Оплата через Stripe Checkout (сторінка оплати Stripe: картки, Apple Pay, Google Pay).

Змінні середовища:
  STRIPE_SECRET_KEY      — секретний ключ (sk_test_... для тестів, sk_live_... для справжніх оплат)
  STRIPE_WEBHOOK_SECRET  — секрет вебхука (whsec_...), Stripe → Developers → Webhooks
"""

import json
import os
import time

import stripe

# Stripe приймає суму в найменших одиницях (центи, пенси, копійки)
CHECKOUT_TTL = 60 * 60   # сесія оплати живе 1 годину (мінімум у Stripe — 30 хв)


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
        "client_reference_id": str(order.id),
        "metadata": {"order_id": str(order.id)},
        "payment_intent_data": {"metadata": {"order_id": str(order.id)}},
        "expires_at": int(time.time()) + CHECKOUT_TTL,
    }
    if order.email:
        params["customer_email"] = order.email
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
