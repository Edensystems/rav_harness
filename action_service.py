"""Server-side enable/disable controls for client action buttons."""

from __future__ import annotations

from sqlalchemy.orm import Session

from models import ActionToggle


def seed_action_toggles(db: Session) -> None:
    from billing_service import KNOWN_ACTIONS

    existing = {row.task_type for row in db.query(ActionToggle).all()}
    added = False
    for task_type in KNOWN_ACTIONS:
        if task_type in existing:
            continue
        db.add(ActionToggle(task_type=task_type, enabled=True))
        added = True
    if added:
        db.commit()


def action_enabled_map(db: Session) -> dict[str, bool]:
    seed_action_toggles(db)
    return {row.task_type: bool(row.enabled) for row in db.query(ActionToggle).all()}


def is_action_enabled(db: Session, task_type: str) -> bool:
    from billing_service import KNOWN_ACTIONS

    seed_action_toggles(db)
    if task_type not in KNOWN_ACTIONS:
        return False
    row = db.query(ActionToggle).filter(ActionToggle.task_type == task_type).first()
    if row is None:
        return True
    return bool(row.enabled)


def set_action_enabled(db: Session, task_type: str, enabled: bool) -> ActionToggle:
    from billing_service import KNOWN_ACTIONS

    if task_type not in KNOWN_ACTIONS:
        raise ValueError(f"Unknown action '{task_type}'")
    seed_action_toggles(db)
    row = db.query(ActionToggle).filter(ActionToggle.task_type == task_type).first()
    if row is None:
        row = ActionToggle(task_type=task_type, enabled=enabled)
        db.add(row)
    else:
        row.enabled = enabled
    db.commit()
    db.refresh(row)
    return row
