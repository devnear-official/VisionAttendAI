"""SQLAlchemy 2.x ORM models for VisionAttend-AI PostgreSQL + pgvector database."""

import uuid
from datetime import datetime, date
from typing import List, Optional
from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.database.session import Base


class Student(Base):
    __tablename__ = "students"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(128), unique=True, nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    batch: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="active", server_default="active"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # Relationships
    face_embeddings: Mapped[List["StudentFaceEmbedding"]] = relationship(
        "StudentFaceEmbedding",
        back_populates="student",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    attendance_records: Mapped[List["AttendanceRecord"]] = relationship(
        "AttendanceRecord", back_populates="student"
    )

    __table_args__ = (
        Index("idx_students_active_lookup", "student_id", "status", "deleted_at"),
    )

    def is_deleted(self) -> bool:
        return self.deleted_at is not None or self.status != "active"


class StudentFaceEmbedding(Base):
    __tablename__ = "student_face_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    embedding = mapped_column(Vector(512), nullable=False)
    model_name: Mapped[str] = mapped_column(
        String(64), nullable=False, default="w600k_r50.onnx", server_default="w600k_r50.onnx"
    )
    model_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="buffalo_l", server_default="buffalo_l"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )

    # Relationships
    student: Mapped["Student"] = relationship(
        "Student", back_populates="face_embeddings"
    )

    __table_args__ = (
        Index("idx_embeddings_student_active", "student_id", "is_active"),
        # HNSW cosine distance index for vector similarity search
        Index(
            "idx_student_face_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    device_name: Mapped[str] = mapped_column(String(64), nullable=False)
    device_code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true"), index=True
    )
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    attendance_records: Mapped[List["AttendanceRecord"]] = relationship(
        "AttendanceRecord", back_populates="device"
    )


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    student_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("students.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    student_id_snapshot: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True
    )
    student_name_snapshot: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    attendance_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )
    check_in_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    device_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("devices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    recognition_confidence: Mapped[Optional[float]] = mapped_column(
        Float, nullable=True
    )
    recognition_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="face_recognition", server_default="face_recognition"
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="present", server_default="present"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Relationships
    student: Mapped[Optional["Student"]] = relationship(
        "Student", back_populates="attendance_records"
    )
    device: Mapped[Optional["Device"]] = relationship(
        "Device", back_populates="attendance_records"
    )

    __table_args__ = (
        # Prevent accidental duplicate check-in on the same date for the same student
        UniqueConstraint(
            "student_id_snapshot",
            "attendance_date",
            name="uq_attendance_student_date",
        ),
        Index("idx_attendance_date_device", "attendance_date", "device_id"),
        Index("idx_attendance_student_date", "student_id", "attendance_date"),
    )
