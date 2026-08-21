import os
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from database import SessionLocal
from models import TaskOutput


def create_task_output(
    db: Session,
    user_id: UUID,
    job_id: str,
    task_type: str,
    file_path: str,
    total: int,
) -> TaskOutput:
    filename = os.path.basename(file_path)
    record = TaskOutput(
        user_id=user_id,
        job_id=job_id,
        task_type=task_type,
        filename=filename,
        file_path=file_path,
        status="running",
        processed=0,
        total=total,
        file_size=0,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def finalize_task_output(job_id: str, status: str, processed: int, total: int) -> None:
    db = SessionLocal()
    try:
        record = db.query(TaskOutput).filter(TaskOutput.job_id == job_id).first()
        if not record:
            return
        record.status = status
        record.processed = processed
        record.total = total
        record.completed_at = datetime.now(timezone.utc)
        if os.path.isfile(record.file_path):
            record.file_size = os.path.getsize(record.file_path)
        db.commit()
    finally:
        db.close()


def build_user_output_path(user_id: UUID, job_id: str, task_type: str) -> str:
    user_dir = os.path.join("server_outputs", str(user_id))
    os.makedirs(user_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(user_dir, f"{task_type}_output_{timestamp}_{job_id[:8]}.txt")
