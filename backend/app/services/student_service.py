"""Student CRUD and profile management service."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database.models import AttendanceRecord, Student, StudentFaceEmbedding
from app.schemas.student import StudentCreate, StudentUpdate
from app.services.embedding_service import EmbeddingService
from app.utils.logger import logger


class StudentService:
    """Manages student records and soft-deletion lifecycle."""

    @staticmethod
    def get_by_student_id(
        db: Session, student_id: str, include_deleted: bool = False
    ) -> Optional[Student]:
        """Lookup student by institutional student_id string."""
        stmt = select(Student).where(Student.student_id == student_id)
        if not include_deleted:
            stmt = stmt.where(Student.deleted_at.is_(None), Student.status == "active")
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_uuid(
        db: Session, student_uuid: uuid.UUID, include_deleted: bool = False
    ) -> Optional[Student]:
        """Lookup student by internal UUID primary key."""
        stmt = select(Student).where(Student.id == student_uuid)
        if not include_deleted:
            stmt = stmt.where(Student.deleted_at.is_(None), Student.status == "active")
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def list_students(
        db: Session,
        skip: int = 0,
        limit: int = 50,
        status_filter: Optional[str] = None,
        search: Optional[str] = None,
        department: Optional[str] = None,
        batch: Optional[str] = None,
        include_deleted: bool = False,
    ) -> Tuple[List[Student], int]:
        """List students with pagination and optional filtering."""
        stmt = select(Student)
        if not include_deleted:
            stmt = stmt.where(Student.deleted_at.is_(None))
        if status_filter:
            stmt = stmt.where(Student.status == status_filter)
        if search:
            search_term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    Student.student_id.ilike(search_term),
                    Student.full_name.ilike(search_term),
                )
            )
        if department:
            stmt = stmt.where(Student.department == department.strip())
        if batch:
            stmt = stmt.where(Student.batch == batch.strip())

        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
        students = db.execute(stmt.order_by(Student.student_id.asc()).offset(skip).limit(limit)).scalars().all()
        return list(students), total

    @staticmethod
    def create_student(db: Session, student_in: StudentCreate) -> Student:
        """Create a new student profile."""
        student = Student(
            student_id=student_in.student_id.strip(),
            full_name=student_in.full_name.strip(),
            email=str(student_in.email).strip().lower() if student_in.email else None,
            department=student_in.department.strip() if student_in.department else None,
            batch=student_in.batch.strip() if student_in.batch else None,
            phone=student_in.phone.strip() if student_in.phone else None,
            status="active",
        )
        db.add(student)
        db.flush()
        logger.info(f"Created student record: {student.student_id} (UUID: {student.id})")
        return student

    @staticmethod
    def update_student(
        db: Session, student_id: str, update_in: StudentUpdate
    ) -> Optional[Student]:
        """Update an existing student profile."""
        student = StudentService.get_by_student_id(db, student_id, include_deleted=True)
        if not student:
            return None

        update_dict = update_in.model_dump(exclude_unset=True)
        for key, val in update_dict.items():
            if val is not None and hasattr(student, key):
                setattr(student, key, val)

        student.updated_at = datetime.now(timezone.utc)
        db.flush()
        logger.info(f"Updated student record: {student.student_id}")
        return student

    @staticmethod
    def soft_delete_student(db: Session, student_id: str) -> Optional[Student]:
        """
        Soft-delete a student and deactivate biometric embeddings.
        Preserves historical attendance records in attendance_records table.
        """
        student = StudentService.get_by_student_id(db, student_id, include_deleted=False)
        if not student:
            return None

        student.deleted_at = datetime.now(timezone.utc)
        student.status = "inactive"
        EmbeddingService.deactivate_embeddings(db, student.id)
        db.flush()
        logger.info(f"Soft-deleted student: {student.student_id} (UUID: {student.id})")
        return student

    @staticmethod
    def count_active_embeddings(db: Session, student_uuid: uuid.UUID) -> int:
        """Count active face embeddings for a student."""
        stmt = (
            select(func.count(StudentFaceEmbedding.id))
            .where(
                StudentFaceEmbedding.student_id == student_uuid,
                StudentFaceEmbedding.is_active.is_(True),
            )
        )
        return db.execute(stmt).scalar() or 0

    @staticmethod
    def get_student_attendance_stats(
        db: Session, student_id: str, student_uuid: uuid.UUID
    ) -> Tuple[int, Optional[datetime]]:
        """Get attendance check-in count and last attendance datetime for a student."""
        stmt = (
            select(
                func.count(AttendanceRecord.id),
                func.max(AttendanceRecord.check_in_time),
            )
            .where(
                or_(
                    AttendanceRecord.student_id == student_uuid,
                    AttendanceRecord.student_id_snapshot == student_id,
                )
            )
        )
        row = db.execute(stmt).first()
        if not row:
            return 0, None
        return int(row[0] or 0), row[1]
