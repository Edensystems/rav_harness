import os
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import TaskOutput, User
from schemas import TaskOutputDetailResponse, TaskOutputResponse

router = APIRouter(prefix="/api/outputs", tags=["outputs"])


@router.get("", response_model=list[TaskOutputResponse])
def list_outputs(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    outputs = (
        db.query(TaskOutput)
        .filter(TaskOutput.user_id == user.id)
        .order_by(TaskOutput.created_at.desc())
        .all()
    )
    return [TaskOutputResponse.model_validate(item) for item in outputs]


@router.get("/{output_id}", response_model=TaskOutputDetailResponse)
def get_output(output_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.query(TaskOutput).filter(TaskOutput.id == output_id, TaskOutput.user_id == user.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Output file not found")

    content = ""
    if os.path.isfile(record.file_path):
        with open(record.file_path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()

    return TaskOutputDetailResponse(
        id=record.id,
        job_id=record.job_id,
        task_type=record.task_type,
        filename=record.filename,
        status=record.status,
        processed=record.processed,
        total=record.total,
        file_size=record.file_size,
        created_at=record.created_at,
        completed_at=record.completed_at,
        content=content,
    )


@router.get("/{output_id}/download")
def download_output(output_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    record = db.query(TaskOutput).filter(TaskOutput.id == output_id, TaskOutput.user_id == user.id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Output file not found")
    if not os.path.isfile(record.file_path):
        raise HTTPException(status_code=404, detail="Output file missing on server")

    return FileResponse(
        record.file_path,
        media_type="text/plain",
        filename=record.filename,
    )
