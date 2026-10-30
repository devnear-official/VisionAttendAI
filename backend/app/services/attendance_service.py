"""Attendance ledger and check-in management service."""

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import AttendanceRecord, Student
from app.utils.logger import logger


class AttendanceService:
    """Manages immutable attendance records and duplicate check-in prevention."""

    @staticmethod
    def get_record_by_id(
        db: Session, record_id: uuid.UUID
    ) -> Optional[AttendanceRecord]:
        """Fetch single attendance record by primary key."""
        stmt = select(AttendanceRecord).where(AttendanceRecord.id == record_id)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def check_existing_attendance(
        db: Session, student_id_snapshot: str, attendance_date: date
    ) -> Optional[AttendanceRecord]:
        """Check if an attendance record already exists for this student on the specified date."""
        stmt = select(AttendanceRecord).where(
            AttendanceRecord.student_id_snapshot == student_id_snapshot,
            AttendanceRecord.attendance_date == attendance_date,
        )
        return db.execute(stmt).scalar_one_or_none()

    @classmethod
    def record_attendance(
        cls,
        db: Session,
        student: Student,
        device_id: Optional[uuid.UUID] = None,
        confidence: Optional[float] = None,
        method: str = "face_recognition",
        status: str = "present",
        check_in_time: Optional[datetime] = None,
    ) -> Tuple[AttendanceRecord, bool]:
        """
        Record attendance transactionally.
        Returns: (AttendanceRecord, was_newly_recorded: bool)
        If student already checked in for today, returns existing record and False.
        """
        now = check_in_time or datetime.now(timezone.utc)
        today = now.date()

        # Duplicate check-in prevention
        existing = cls.check_existing_attendance(db, student.student_id, today)
        if existing is not None:
            logger.info(
                f"Attendance already marked for student '{student.student_id}' on {today}. "
                f"Existing check-in at {existing.check_in_time}."
            )
            return existing, False

        record = AttendanceRecord(
            student_id=student.id,
            student_id_snapshot=student.student_id,
            student_name_snapshot=student.full_name,
            attendance_date=today,
            check_in_time=now,
            device_id=device_id,
            recognition_confidence=confidence,
            recognition_method=method,
            status=status,
        )
        db.add(record)
        db.flush()
        logger.info(
            f"Successfully recorded attendance: student='{student.student_id}', "
            f"date={today}, time={now.isoformat()}"
        )
        return record, True

    @staticmethod
    def list_attendance(
        db: Session,
        date_filter: Optional[date] = None,
        student_id_filter: Optional[str] = None,
        device_id_filter: Optional[uuid.UUID] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AttendanceRecord], int]:
        """List attendance records with optional filtering and pagination."""
        stmt = select(AttendanceRecord)
        if date_filter:
            stmt = stmt.where(AttendanceRecord.attendance_date == date_filter)
        if student_id_filter:
            stmt = stmt.where(AttendanceRecord.student_id_snapshot == student_id_filter)
        if device_id_filter:
            stmt = stmt.where(AttendanceRecord.device_id == device_id_filter)

        total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar() or 0
        records = (
            db.execute(stmt.order_by(AttendanceRecord.check_in_time.desc()).offset(skip).limit(limit))
            .scalars()
            .all()
        )
        return list(records), total
