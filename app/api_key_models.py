from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProjectAPIKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("API key name cannot be empty")

        return cleaned


class ProjectAPIKeyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    created_by_user_id: int | None
    last_used_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class ProjectAPIKeyCreateResponse(BaseModel):
    id: int
    project_id: int
    name: str
    api_key: str
    created_at: datetime


class ProjectAPIKeyListResponse(BaseModel):
    api_keys: list[ProjectAPIKeyResponse]
    total: int