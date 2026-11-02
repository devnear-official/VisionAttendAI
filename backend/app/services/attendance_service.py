"""Attendance ledger and check-in management service."""

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional, Tuple
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database.models import AttendanceRecord, Device, Student
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
    def delete_record(db: Session, record_id: uuid.UUID) -> Optional[AttendanceRecord]:
        """Delete an attendance record by ID so the student can be re-verified today."""
        record = db.execute(
            select(AttendanceRecord).where(AttendanceRecord.id == record_id)
        ).scalar_one_or_none()
        if not record:
            return None
        db.delete(record)
        db.flush()
        logger.info(
            f"Deleted attendance record {record_id} for student '{record.student_id_snapshot}' on {record.attendance_date}."
        )
        return record

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
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        search: Optional[str] = None,
        student_id_filter: Optional[str] = None,
        device_id_filter: Optional[uuid.UUID] = None,
        department: Optional[str] = None,
        batch: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Tuple[List[AttendanceRecord], int]:
        """List attendance records with optional filtering and pagination."""
        stmt = select(AttendanceRecord).options(
            joinedload(AttendanceRecord.device),
            joinedload(AttendanceRecord.student),
        )

        if department or batch:
            stmt = stmt.outerjoin(Student, AttendanceRecord.student_id == Student.id)
            if department:
                stmt = stmt.where(Student.department == department.strip())
            if batch:
                stmt = stmt.where(Student.batch == batch.strip())

        if date_filter:
            stmt = stmt.where(AttendanceRecord.attendance_date == date_filter)
        if start_date:
            stmt = stmt.where(AttendanceRecord.attendance_date >= start_date)
        if end_date:
            stmt = stmt.where(AttendanceRecord.attendance_date <= end_date)

        if search:
            search_term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    AttendanceRecord.student_id_snapshot.ilike(search_term),
                    AttendanceRecord.student_name_snapshot.ilike(search_term),
                )
            )
        if student_id_filter:
            stmt = stmt.where(AttendanceRecord.student_id_snapshot == student_id_filter.strip())
        if device_id_filter:
            stmt = stmt.where(AttendanceRecord.device_id == device_id_filter)

        count_stmt = select(func.count(AttendanceRecord.id))
        if department or batch:
            count_stmt = count_stmt.select_from(AttendanceRecord).outerjoin(
                Student, AttendanceRecord.student_id == Student.id
            )
            if department:
                count_stmt = count_stmt.where(Student.department == department.strip())
            if batch:
                count_stmt = count_stmt.where(Student.batch == batch.strip())
        else:
            count_stmt = count_stmt.select_from(AttendanceRecord)

        if date_filter:
            count_stmt = count_stmt.where(AttendanceRecord.attendance_date == date_filter)
        if start_date:
            count_stmt = count_stmt.where(AttendanceRecord.attendance_date >= start_date)
        if end_date:
            count_stmt = count_stmt.where(AttendanceRecord.attendance_date <= end_date)
        if search:
            search_term = f"%{search.strip()}%"
            count_stmt = count_stmt.where(
                or_(
                    AttendanceRecord.student_id_snapshot.ilike(search_term),
                    AttendanceRecord.student_name_snapshot.ilike(search_term),
                )
            )
        if student_id_filter:
            count_stmt = count_stmt.where(AttendanceRecord.student_id_snapshot == student_id_filter.strip())
        if device_id_filter:
            count_stmt = count_stmt.where(AttendanceRecord.device_id == device_id_filter)

        total = db.execute(count_stmt).scalar() or 0
        records = (
            db.execute(stmt.order_by(AttendanceRecord.check_in_time.desc()).offset(skip).limit(limit))
            .scalars()
            .all()
        )
        return list(records), total
