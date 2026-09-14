from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from action_service import set_action_enabled
from billing_service import list_action_rates, set_action_rate, set_user_credits
from config import get_task_connections, set_task_connections
from database import get_db
from dependencies import require_admin
from models import User, UserList
from payment_service import get_payment_settings, set_payment_settings
from schemas import (
    ActionRateResponse,
    ActionRateUpdate,
    ActionToggleUpdate,
    AdminCreditUpdate,
    AdminUserResponse,
    PaymentSettingsResponse,
    PaymentSettingsUpdate,
    TaskConnectionsResponse,
    TaskConnectionsUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    result = []
    for user in users:
        list_count = db.query(UserList).filter(UserList.user_id == user.id).count()
        result.append(
            AdminUserResponse(
                id=user.id,
                email=user.email,
                phone_number=user.phone_number,
                credits=float(user.credits),
                status=user.status.value,
                role=user.role.value,
                list_count=list_count,
            )
        )
    return result


@router.patch("/users/{user_id}/credits", response_model=AdminUserResponse)
def update_user_credits(
    user_id: UUID,
    payload: AdminCreditUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if payload.credits is None and payload.delta is None:
        raise HTTPException(status_code=400, detail="Provide credits or delta")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        updated = set_user_credits(
            db,
            user,
            credits=payload.credits,
            delta=payload.delta,
            note=payload.note or f"Updated by {admin.email}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    list_count = db.query(UserList).filter(UserList.user_id == user.id).count()
    return AdminUserResponse(
        id=updated.id,
        email=updated.email,
        phone_number=updated.phone_number,
        credits=float(updated.credits),
        status=updated.status.value,
        role=updated.role.value,
        list_count=list_count,
    )


@router.get("/billing", response_model=list[ActionRateResponse])
def admin_list_billing(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return [ActionRateResponse(**item) for item in list_action_rates(db)]


@router.put("/billing", response_model=ActionRateResponse)
def admin_update_billing(
    payload: ActionRateUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        set_action_rate(db, payload.task_type, payload.rate)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    catalog = {item["task_type"]: item for item in list_action_rates(db)}
    return ActionRateResponse(**catalog[payload.task_type])


@router.get("/connections", response_model=TaskConnectionsResponse)
def admin_get_connections(admin: User = Depends(require_admin)):
    return TaskConnectionsResponse(connections=get_task_connections())


@router.put("/connections", response_model=TaskConnectionsResponse)
def admin_set_connections(payload: TaskConnectionsUpdate, admin: User = Depends(require_admin)):
    return TaskConnectionsResponse(connections=set_task_connections(payload.connections))


@router.put("/actions", response_model=ActionRateResponse)
def admin_set_action_enabled(
    payload: ActionToggleUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    try:
        set_action_enabled(db, payload.task_type, payload.enabled)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    catalog = {item["task_type"]: item for item in list_action_rates(db)}
    return ActionRateResponse(**catalog[payload.task_type])


@router.get("/payments", response_model=PaymentSettingsResponse)
def admin_get_payments(admin: User = Depends(require_admin)):
    return PaymentSettingsResponse(**get_payment_settings())


@router.put("/payments", response_model=PaymentSettingsResponse)
def admin_set_payments(payload: PaymentSettingsUpdate, admin: User = Depends(require_admin)):
    updated = set_payment_settings(payload.model_dump(exclude_unset=True))
    return PaymentSettingsResponse(**updated)
