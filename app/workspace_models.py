
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    description: str | None
    is_active: bool
    created_at: datetime


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    slug: str
    workspace_type: Literal["personal", "organization"]
    role: Literal["org_admin", "developer", "viewer"]
    created_at: datetime
    projects: list[WorkspaceProjectResponse]


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceResponse]
    total: int


class WorkspaceSelectionRequest(BaseModel):
    organization_id: int = Field(gt=0)


class CurrentWorkspaceResponse(BaseModel):
    workspace: WorkspaceResponse | None
