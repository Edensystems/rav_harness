"""Live payment instructions loaded from environment variables."""

from __future__ import annotations

import os
import re
from urllib.parse import quote

from dotenv import dotenv_values

PAYMENT_KEYS = {
    "crypto_coin": "PAYMENT_CRYPTO_COIN",
    "crypto_network": "PAYMENT_CRYPTO_NETWORK",
    "crypto_address": "PAYMENT_CRYPTO_ADDRESS",
    "whatsapp_number": "PAYMENT_WHATSAPP_NUMBER",
    "whatsapp_message": "PAYMENT_WHATSAPP_MESSAGE",
}

DEFAULTS = {
    "crypto_coin": "USDT",
    "crypto_network": "TRC20",
    "crypto_address": "",
    "whatsapp_number": "",
    "whatsapp_message": "Hi, I want to add credits to my account ({email}). Current balance: {credits}.",
}


def _read_live(env_key: str, default: str) -> str:
    raw = os.getenv(env_key)
    if raw is None or str(raw).strip() == "":
        raw = dotenv_values(".env").get(env_key)
    if raw is None:
        return default
    return str(raw).strip()


def get_payment_settings() -> dict:
    return {field: _read_live(env_key, DEFAULTS[field]) for field, env_key in PAYMENT_KEYS.items()}


def set_payment_settings(payload: dict) -> dict:
    current = get_payment_settings()
    for field, env_key in PAYMENT_KEYS.items():
        if field not in payload or payload[field] is None:
            continue
        value = str(payload[field]).strip()
        os.environ[env_key] = value
        current[field] = value
    return current


def _digits_phone(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    return digits


def public_payment_options(*, email: str, credits) -> dict:
    settings = get_payment_settings()
    address = settings["crypto_address"]
    coin = settings["crypto_coin"] or DEFAULTS["crypto_coin"]
    network = settings["crypto_network"]
    number = _digits_phone(settings["whatsapp_number"])
    template = settings["whatsapp_message"] or DEFAULTS["whatsapp_message"]
    try:
        message = template.format(email=email, credits=credits)
    except (KeyError, IndexError, ValueError):
        message = f"{template} Account: {email}. Credits: {credits}."

    whatsapp_url = ""
    if number:
        whatsapp_url = f"https://wa.me/{number}?text={quote(message)}"

    return {
        "crypto": {
            "coin": coin,
            "network": network,
            "address": address,
            "configured": bool(address),
        },
        "whatsapp": {
            "number": number,
            "message": message,
            "url": whatsapp_url,
            "configured": bool(number),
        },
    }
