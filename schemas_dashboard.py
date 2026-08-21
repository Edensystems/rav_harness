from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    total_runs: int
    active_runs: int
    completed_runs: int
    stopped_runs: int
    success_rate: float | None
    items_processed: int
    items_total: int
    list_count: int
    last_run_at: datetime | None
    credits: float
