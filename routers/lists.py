from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from models import ListItem, User, UserList
from schemas import (
    ListItemCreate,
    ListItemResponse,
    MessageResponse,
    UserListCreate,
    UserListResponse,
    UserListUpdate,
)

router = APIRouter(prefix="/api/lists", tags=["lists"])


def _serialize_list(user_list: UserList) -> UserListResponse:
    return UserListResponse(
        id=user_list.id,
        name=user_list.name,
        items=[ListItemResponse.model_validate(item) for item in user_list.items],
        created_at=user_list.created_at,
        updated_at=user_list.updated_at,
    )


@router.get("", response_model=list[UserListResponse])
def list_user_lists(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lists = db.query(UserList).filter(UserList.user_id == user.id).order_by(UserList.created_at.desc()).all()
    return [_serialize_list(lst) for lst in lists]


@router.post("", response_model=UserListResponse, status_code=201)
def create_user_list(
    payload: UserListCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_list = UserList(user_id=user.id, name=payload.name.strip())
    db.add(user_list)
    db.flush()

    for index, value in enumerate(payload.items):
        cleaned = value.strip()
        if cleaned:
            db.add(ListItem(list_id=user_list.id, value=cleaned, sort_order=index))

    db.commit()
    db.refresh(user_list)
    return _serialize_list(user_list)


@router.put("/{list_id}", response_model=UserListResponse)
def replace_user_list(
    list_id: UUID,
    payload: UserListUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_list = db.query(UserList).filter(UserList.id == list_id, UserList.user_id == user.id).first()
    if not user_list:
        raise HTTPException(status_code=404, detail="List not found")

    if payload.name is not None:
        user_list.name = payload.name.strip()

    for item in list(user_list.items):
        db.delete(item)
    db.flush()

    for index, value in enumerate(payload.items):
        cleaned = value.strip()
        if cleaned:
            db.add(ListItem(list_id=user_list.id, value=cleaned, sort_order=index))

    db.commit()
    db.refresh(user_list)
    return _serialize_list(user_list)


@router.get("/{list_id}", response_model=UserListResponse)
def get_user_list(list_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_list = db.query(UserList).filter(UserList.id == list_id, UserList.user_id == user.id).first()
    if not user_list:
        raise HTTPException(status_code=404, detail="List not found")
    return _serialize_list(user_list)


@router.post("/{list_id}/items", response_model=ListItemResponse, status_code=201)
def add_list_item(
    list_id: UUID,
    payload: ListItemCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user_list = db.query(UserList).filter(UserList.id == list_id, UserList.user_id == user.id).first()
    if not user_list:
        raise HTTPException(status_code=404, detail="List not found")

    next_order = len(user_list.items)
    item = ListItem(list_id=user_list.id, value=payload.value.strip(), sort_order=next_order)
    db.add(item)
    db.commit()
    db.refresh(item)
    return ListItemResponse.model_validate(item)


@router.delete("/{list_id}", response_model=MessageResponse)
def delete_user_list(list_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    user_list = db.query(UserList).filter(UserList.id == list_id, UserList.user_id == user.id).first()
    if not user_list:
        raise HTTPException(status_code=404, detail="List not found")
    db.delete(user_list)
    db.commit()
    return MessageResponse(message="List deleted")


@router.delete("/{list_id}/items/{item_id}", response_model=MessageResponse)
def delete_list_item(
    list_id: UUID,
    item_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    item = (
        db.query(ListItem)
        .join(UserList)
        .filter(ListItem.id == item_id, UserList.id == list_id, UserList.user_id == user.id)
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    db.delete(item)
    db.commit()
    return MessageResponse(message="Item deleted")
