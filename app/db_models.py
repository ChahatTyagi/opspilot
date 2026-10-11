
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, index=True
    )
    title: Mapped[str] = mapped_column(
        String(150), nullable=False
    )
    description: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    service: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="open", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )