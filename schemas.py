import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone_number: str | None = Field(default=None, max_length=32)

    @field_validator("phone_number")
    @classmethod
    def strip_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    device_id: str = Field(min_length=8, max_length=64)
    device_name: str = Field(default="Desktop Client", max_length=120)


class AuthUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    phone_number: str | None
    credits: float
    status: str
    role: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: AuthUserResponse


class MessageResponse(BaseModel):
    message: str


class ListItemCreate(BaseModel):
    value: str = Field(min_length=1, max_length=500)


class ListItemResponse(BaseModel):
    id: uuid.UUID
    value: str
    sort_order: int

    model_config = {"from_attributes": True}


class UserListCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    items: list[str] = Field(default_factory=list)


class UserListUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    items: list[str] = Field(default_factory=list)


class UserListResponse(BaseModel):
    id: uuid.UUID
    name: str
    items: list[ListItemResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskOutputResponse(BaseModel):
    id: uuid.UUID
    job_id: str
    task_type: str
    filename: str
    status: str
    processed: int
    total: int
    file_size: int
    created_at: datetime
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskOutputDetailResponse(TaskOutputResponse):
    content: str


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    phone_number: str | None
    credits: float
    status: str
    role: str
    list_count: int = 0

    model_config = {"from_attributes": True}


class TaskPayload(BaseModel):
    task_type: str
    target_numbers: list[str]
    target_password: str
    share_code: str = ""
    amount: str = ""
    use_bonus: bool = False
    use_total_balance: bool = False
    connections: int = 3
    output_filename: str = ""


class ActionRateResponse(BaseModel):
    task_type: str
    label: str
    rate: float
    billable: bool


class BillingCatalogResponse(BaseModel):
    credits: float
    rates: list[ActionRateResponse]


class ActionRateUpdate(BaseModel):
    task_type: str = Field(min_length=1, max_length=64)
    rate: float = Field(ge=0, le=10000)


class AdminCreditUpdate(BaseModel):
    credits: float | None = Field(default=None, ge=0, le=1000000)
    delta: float | None = Field(default=None, ge=-1000000, le=1000000)
    note: str = Field(default="Admin credit update", max_length=255)
