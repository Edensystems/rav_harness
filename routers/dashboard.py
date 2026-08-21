from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import TaskOutput, User, UserList
from schemas_dashboard import DashboardStatsResponse

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=DashboardStatsResponse)
def dashboard_stats(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    outputs = db.query(TaskOutput).filter(TaskOutput.user_id == user.id).all()
    list_count = db.query(UserList).filter(UserList.user_id == user.id).count()

    total_runs = len(outputs)
    active_runs = sum(1 for item in outputs if item.status == "running")
    completed_runs = sum(1 for item in outputs if item.status == "completed")
    stopped_runs = sum(1 for item in outputs if item.status == "stopped")
    items_processed = sum(item.processed for item in outputs)
    items_total = sum(item.total for item in outputs)

    finished = completed_runs + stopped_runs
    success_rate = round((completed_runs / finished) * 100, 1) if finished else None

    last_run_at = None
    if outputs:
        last_run_at = max(item.created_at for item in outputs)

    return DashboardStatsResponse(
        total_runs=total_runs,
        active_runs=active_runs,
        completed_runs=completed_runs,
        stopped_runs=stopped_runs,
        success_rate=success_rate,
        items_processed=items_processed,
        items_total=items_total,
        list_count=list_count,
        last_run_at=last_run_at,
        credits=float(user.credits),
    )
