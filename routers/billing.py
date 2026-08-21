from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from billing_service import list_action_rates
from database import get_db
from dependencies import get_current_user
from models import User
from schemas import ActionRateResponse, BillingCatalogResponse

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("", response_model=BillingCatalogResponse)
def billing_catalog(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return BillingCatalogResponse(
        credits=float(user.credits),
        rates=[ActionRateResponse(**item) for item in list_action_rates(db)],
    )
