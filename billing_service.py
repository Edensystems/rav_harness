"""Per-action credit rates and charging for successful automation work."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from sqlalchemy.orm import Session

from models import ActionRate, CreditLedger, User

CHARGE_LOCK = threading.Lock()

KNOWN_ACTIONS = (
    "balance",
    "bet",
    "rollover",
    "virtual_bet",
    "app_bonus",
    "claim_bonus",
    "claim",
    "save_token",
)

ACTION_LABELS = {
    "balance": "Check Balances",
    "bet": "Place Bets",
    "rollover": "Rollover Bet",
    "virtual_bet": "Place Arbitrage Bet",
    "app_bonus": "App Bonus Claim",
    "claim_bonus": "Claim Bonus",
    "claim": "Claim Winnings",
    "save_token": "Save Tokens",
}

DEFAULT_RATES = {
    "balance": "0",
    "bet": "1",
    "rollover": "0",
    "virtual_bet": "0",
    "app_bonus": "0",
    "claim_bonus": "0",
    "claim": "0",
    "save_token": "0",
}


def to_credits(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def format_credits(value) -> str:
    number = to_credits(value)
    text = format(number.normalize(), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


@dataclass(frozen=True)
class ChargeResult:
    charged: bool
    amount: Decimal
    balance: Decimal
    reason: str = ""


def seed_action_rates(db: Session) -> None:
    existing = {row.task_type for row in db.query(ActionRate).all()}
    added = False
    for task_type, rate in DEFAULT_RATES.items():
        if task_type in existing:
            continue
        db.add(ActionRate(task_type=task_type, rate=to_credits(rate)))
        added = True
    if added:
        db.commit()


def get_action_rate(db: Session, task_type: str) -> Decimal:
    row = db.query(ActionRate).filter(ActionRate.task_type == task_type).first()
    if row is None:
        return to_credits(DEFAULT_RATES.get(task_type, "0"))
    return to_credits(row.rate)


def list_action_rates(db: Session) -> list[dict]:
    seed_action_rates(db)
    rows = {row.task_type: row for row in db.query(ActionRate).all()}
    catalog = []
    for task_type in KNOWN_ACTIONS:
        rate = to_credits(rows[task_type].rate) if task_type in rows else to_credits(DEFAULT_RATES[task_type])
        catalog.append(
            {
                "task_type": task_type,
                "label": ACTION_LABELS.get(task_type, task_type),
                "rate": float(rate),
                "billable": rate > 0,
            }
        )
    return catalog


def set_action_rate(db: Session, task_type: str, rate) -> ActionRate:
    if task_type not in KNOWN_ACTIONS:
        raise ValueError(f"Unknown action '{task_type}'")
    value = to_credits(rate)
    if value < 0:
        raise ValueError("Rate cannot be negative")
    row = db.query(ActionRate).filter(ActionRate.task_type == task_type).first()
    if row is None:
        row = ActionRate(task_type=task_type, rate=value)
        db.add(row)
    else:
        row.rate = value
    db.commit()
    db.refresh(row)
    return row


def set_user_credits(db: Session, user: User, *, credits=None, delta=None, note: str = "Admin credit update") -> User:
    current = to_credits(user.credits)
    if credits is not None:
        new_balance = to_credits(credits)
    elif delta is not None:
        new_balance = current + to_credits(delta)
    else:
        raise ValueError("Provide credits or delta")
    if new_balance < 0:
        raise ValueError("Credits cannot be negative")

    amount = new_balance - current
    user.credits = new_balance
    db.add(
        CreditLedger(
            user_id=user.id,
            job_id=None,
            task_type="admin",
            amount=amount,
            balance_after=new_balance,
            note=note,
        )
    )
    db.commit()
    db.refresh(user)
    return user


def charge_successful_action(
    user_id: str | UUID,
    task_type: str,
    job_id: str,
    rate,
    note: str = "",
    db: Session | None = None,
) -> ChargeResult:
    from database import SessionLocal

    amount = to_credits(rate)
    if amount <= 0:
        return ChargeResult(charged=False, amount=amount, balance=Decimal("0"), reason="not_billable")

    close = False
    if db is None:
        db = SessionLocal()
        close = True

    with CHARGE_LOCK:
        try:
            uid = user_id if isinstance(user_id, UUID) else UUID(str(user_id))
            query = db.query(User).filter(User.id == uid)
            try:
                user = query.with_for_update().first()
            except Exception:
                user = query.first()
            if not user:
                return ChargeResult(charged=False, amount=amount, balance=Decimal("0"), reason="user_not_found")

            balance = to_credits(user.credits)
            if balance < amount:
                return ChargeResult(charged=False, amount=amount, balance=balance, reason="insufficient_credits")

            new_balance = balance - amount
            user.credits = new_balance
            db.add(
                CreditLedger(
                    user_id=user.id,
                    job_id=job_id,
                    task_type=task_type,
                    amount=-amount,
                    balance_after=new_balance,
                    note=note or f"Successful {task_type}",
                )
            )
            db.commit()
            return ChargeResult(charged=True, amount=amount, balance=new_balance)
        except Exception:
            db.rollback()
            raise
        finally:
            if close:
                db.close()
