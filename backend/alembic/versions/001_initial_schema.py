"""Initial schema: students, devices, student_face_embeddings, attendance_records with pgvector HNSW index.

Revision ID: 001_initial_schema
Revises: 
Create Date: 2026-10-30 12:35:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Ensure pgvector extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Table: students
    op.create_table(
        "students",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("student_id", sa.String(length=32), nullable=False),
        sa.Column("full_name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=128), nullable=True),
        sa.Column("department", sa.String(length=64), nullable=True),
        sa.Column("batch", sa.String(length=32), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("student_id", name="uq_students_student_id"),
        sa.UniqueConstraint("email", name="uq_students_email"),
    )
    op.create_index("idx_students_student_id", "students", ["student_id"])
    op.create_index("idx_students_deleted_at", "students", ["deleted_at"])
    op.create_index("idx_students_active_lookup", "students", ["student_id", "status", "deleted_at"])

    # 3. Table: devices
    op.create_table(
        "devices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("device_name", sa.String(length=64), nullable=False),
        sa.Column("device_code", sa.String(length=64), nullable=False),
        sa.Column("api_key_hash", sa.String(length=128), nullable=False),
        sa.Column("location", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("device_code", name="uq_devices_device_code"),
    )
    op.create_index("idx_devices_device_code", "devices", ["device_code"])
    op.create_index("idx_devices_is_active", "devices", ["is_active"])

    # 4. Table: student_face_embeddings
    op.create_table(
        "student_face_embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            sa.ForeignKey("students.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("embedding", Vector(512), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False, server_default="w600k_r50.onnx"),
        sa.Column("model_version", sa.String(length=32), nullable=False, server_default="buffalo_l"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.create_index("idx_embeddings_student_id", "student_face_embeddings", ["student_id"])
    op.create_index("idx_embeddings_is_active", "student_face_embeddings", ["is_active"])
    op.create_index("idx_embeddings_student_active", "student_face_embeddings", ["student_id", "is_active"])

    # Create HNSW vector cosine similarity index
    op.execute(
        """
        CREATE INDEX idx_student_face_embeddings_hnsw
        ON student_face_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64);
        """
    )

    # 5. Table: attendance_records
    op.create_table(
        "attendance_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "student_id",
            UUID(as_uuid=True),
            sa.ForeignKey("students.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("student_id_snapshot", sa.String(length=32), nullable=False),
        sa.Column("student_name_snapshot", sa.String(length=128), nullable=False),
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("check_in_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "device_id",
            UUID(as_uuid=True),
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("recognition_confidence", sa.Float(), nullable=True),
        sa.Column("recognition_method", sa.String(length=32), nullable=False, server_default="face_recognition"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="present"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("student_id_snapshot", "attendance_date", name="uq_attendance_student_date"),
    )
    op.create_index("idx_attendance_student_id", "attendance_records", ["student_id"])
    op.create_index("idx_attendance_snapshot", "attendance_records", ["student_id_snapshot"])
    op.create_index("idx_attendance_date", "attendance_records", ["attendance_date"])
    op.create_index("idx_attendance_device_id", "attendance_records", ["device_id"])
    op.create_index("idx_attendance_date_device", "attendance_records", ["attendance_date", "device_id"])
    op.create_index("idx_attendance_student_date", "attendance_records", ["student_id", "attendance_date"])


def downgrade() -> None:
    op.drop_table("attendance_records")
    op.execute("DROP INDEX IF EXISTS idx_student_face_embeddings_hnsw;")
    op.drop_table("student_face_embeddings")
    op.drop_table("devices")
    op.drop_table("students")
