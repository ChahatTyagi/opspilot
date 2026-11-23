
from datetime import datetime
from typing import Literal

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class RegisterRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=12, max_length=128)

    account_type: Literal["personal", "organization"]

    organization_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    project_name: str = Field(
        min_length=1,
        max_length=150,
    )

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        cleaned = value.strip()

        if not cleaned:
            raise ValueError("Display name must not be empty")

        return cleaned

    @field_validator("organization_name", "project_name")
    @classmethod
    def validate_optional_names(cls, value: str | None) -> str | None:
        if value is None:
            return None

        cleaned = value.strip()

        if not cleaned:
            raise ValueError("Name must not be empty")

        return cleaned

    @model_validator(mode="after")
    def validate_workspace_details(self):
        if (
            self.account_type == "organization"
            and not self.organization_name
        ):
            raise ValueError(
                "Organization name is required for organization accounts"
            )

        if (
            self.account_type == "personal"
            and self.organization_name is not None
        ):
            raise ValueError(
                "Organization name must not be provided for personal accounts"
            )

        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    display_name: str
    created_at: datetime


class RegistrationResponse(UserResponse):
    workspace_id: int
    workspace_name: str
    workspace_type: Literal["personal", "organization"]
    membership_role: str

    project_id: int
    project_name: str
    project_slug: str
