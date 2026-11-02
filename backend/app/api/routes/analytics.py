"""Institutional attendance metrics and dashboard analytics routes."""

from datetime import datetime, timedelta, timezone
from typing import Dict, List
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.security import verify_admin_key
from app.database.models import AttendanceRecord, Device, Student, StudentFaceEmbedding
from app.database.session import get_db
from app.schemas.analytics import DailyTrendStat, DashboardSummaryResponse, DepartmentStat, ReportsResponse
from app.schemas.attendance import AttendanceResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])


def serialize_recent_record(r: AttendanceRecord) -> AttendanceResponse:
    dev_name = r.device.device_name if getattr(r, "device", None) else None
    dev_code = r.device.device_code if getattr(r, "device", None) else None
    dept = r.student.department if getattr(r, "student", None) else None
    return AttendanceResponse(
        id=r.id,
        student_id=r.student_id,
        student_id_snapshot=r.student_id_snapshot,
        student_name_snapshot=r.student_name_snapshot,
        attendance_date=r.attendance_date,
        check_in_time=r.check_in_time,
        device_id=r.device_id,
        recognition_confidence=r.recognition_confidence,
        recognition_method=r.recognition_method,
        status=r.status,
        device_name=dev_name,
        device_code=dev_code,
        department=dept,
        created_at=r.created_at,
    )


@router.get(
    "/dashboard",
    response_model=DashboardSummaryResponse,
    summary="Get aggregated dashboard metrics",
    description="Calculates real-time attendance KPIs, unique student counts, department distributions, and recent check-ins.",
)
async def get_dashboard_summary(
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
) -> DashboardSummaryResponse:
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()

    # 1. Total registered and total active students
    total_students = (
        db.execute(
            select(func.count(Student.id)).where(Student.deleted_at.is_(None))
        ).scalar()
        or 0
    )

    total_active = (
        db.execute(
            select(func.count(Student.id)).where(
                Student.status == "active",
                Student.deleted_at.is_(None),
            )
        ).scalar()
        or 0
    )

    # 2. Today's attendance counts & unique students
    today_count = (
        db.execute(
            select(func.count(AttendanceRecord.id)).where(
                AttendanceRecord.attendance_date == today
            )
        ).scalar()
        or 0
    )

    unique_present = (
        db.execute(
            select(func.count(func.distinct(AttendanceRecord.student_id_snapshot))).where(
                AttendanceRecord.attendance_date == today
            )
        ).scalar()
        or 0
    )

    # 3. Average confidence score today (fallback to overall if no check-ins today)
    avg_confidence_val = db.execute(
        select(func.avg(AttendanceRecord.recognition_confidence)).where(
            AttendanceRecord.attendance_date == today
        )
    ).scalar()

    if avg_confidence_val is None:
        avg_confidence_val = db.execute(
            select(func.avg(AttendanceRecord.recognition_confidence))
        ).scalar()

    avg_confidence = round(float(avg_confidence_val), 4) if avg_confidence_val is not None else None

    # 4. Overall attendance rate %
    attendance_rate = (
        min(100.0, round((unique_present / total_active) * 100.0, 1)) if total_active > 0 else 0.0
    )

    # 5. Registered face templates in PostgreSQL
    templates_count = (
        db.execute(
            select(func.count(StudentFaceEmbedding.id)).where(
                StudentFaceEmbedding.is_active.is_(True)
            )
        ).scalar()
        or 0
    )

    # 6. Edge Devices (Total and Online via 120s heartbeat window)
    total_devices = (
        db.execute(
            select(func.count(Device.id)).where(Device.is_active.is_(True))
        ).scalar()
        or 0
    )

    cutoff = now_utc - timedelta(seconds=120)
    online_devices = (
        db.execute(
            select(func.count(Device.id)).where(
                Device.is_active.is_(True),
                Device.last_seen_at.is_not(None),
                Device.last_seen_at >= cutoff,
            )
        ).scalar()
        or 0
    )

    # 7. Department Breakdown
    dept_totals_rows = db.execute(
        select(
            Student.department,
            func.count(Student.id).label("total"),
        )
        .where(Student.status == "active", Student.deleted_at.is_(None))
        .group_by(Student.department)
    ).all()

    dept_totals: Dict[str, int] = {
        (row[0] or "Unassigned"): row[1] for row in dept_totals_rows
    }

    dept_presents_rows = db.execute(
        select(
            Student.department,
            func.count(AttendanceRecord.id).label("present"),
        )
        .join(Student, AttendanceRecord.student_id == Student.id)
        .where(
            AttendanceRecord.attendance_date == today,
            Student.status == "active",
            Student.deleted_at.is_(None),
        )
        .group_by(Student.department)
    ).all()

    dept_presents: Dict[str, int] = {
        (row[0] or "Unassigned"): row[1] for row in dept_presents_rows
    }

    department_stats = []
    for dept, total_count in dept_totals.items():
        present_count = dept_presents.get(dept, 0)
        rate = round((present_count / total_count) * 100.0, 1) if total_count > 0 else 0.0
        department_stats.append(
            DepartmentStat(
                department=dept,
                total_students=total_count,
                present_today=present_count,
                attendance_rate=rate,
            )
        )
    department_stats.sort(key=lambda d: d.total_students, reverse=True)

    # 8. Recent attendance check-in records (last 10)
    recent_records = (
        db.execute(
            select(AttendanceRecord)
            .options(
                joinedload(AttendanceRecord.device),
                joinedload(AttendanceRecord.student),
            )
            .order_by(AttendanceRecord.check_in_time.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )

    # 9. Daily attendance trends for the past 14 days
    trends_cutoff = today - timedelta(days=14)
    trends_rows = db.execute(
        select(
            AttendanceRecord.attendance_date,
            func.count(AttendanceRecord.id),
            func.count(func.distinct(AttendanceRecord.student_id_snapshot)),
        )
        .where(AttendanceRecord.attendance_date >= trends_cutoff)
        .group_by(AttendanceRecord.attendance_date)
        .order_by(AttendanceRecord.attendance_date.asc())
    ).all()

    daily_trends = [
        DailyTrendStat(
            date=row[0].isoformat(),
            attendance_count=row[1],
            unique_students=row[2],
        )
        for row in trends_rows
    ]

    return DashboardSummaryResponse(
        total_students=total_students,
        total_active_students=total_active,
        today_attendance_count=today_count,
        unique_students_present=unique_present,
        attendance_rate=attendance_rate,
        average_confidence=avg_confidence,
        registered_face_templates=templates_count,
        total_devices=total_devices,
        online_devices=online_devices,
        departments=department_stats,
        recent_activity=[serialize_recent_record(r) for r in recent_records],
        attendance_trends=daily_trends,
    )


@router.get(
    "/reports",
    response_model=ReportsResponse,
    summary="Get aggregated attendance reports and trends",
    description="Returns institutional 30-day attendance metrics, department summaries, and daily trends.",
)
async def get_attendance_reports(
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
) -> ReportsResponse:
    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    month_ago = today - timedelta(days=30)

    # Total active students
    total_active = (
        db.execute(
            select(func.count(Student.id)).where(
                Student.status == "active",
                Student.deleted_at.is_(None),
            )
        ).scalar()
        or 0
    )

    # Registered face templates
    templates_count = (
        db.execute(
            select(func.count(StudentFaceEmbedding.id)).where(
                StudentFaceEmbedding.is_active.is_(True)
            )
        ).scalar()
        or 0
    )

    # Total monthly check-ins
    total_monthly = (
        db.execute(
            select(func.count(AttendanceRecord.id)).where(
                AttendanceRecord.attendance_date >= month_ago
            )
        ).scalar()
        or 0
    )

    # Mean recognition quality across all check-ins
    avg_conf = (
        db.execute(
            select(func.avg(AttendanceRecord.recognition_confidence)).where(
                AttendanceRecord.attendance_date >= month_ago
            )
        ).scalar()
    )
    if avg_conf is None:
        avg_conf = db.execute(select(func.avg(AttendanceRecord.recognition_confidence))).scalar()
    mean_confidence = round(float(avg_conf), 4) if avg_conf is not None else 0.85

    # Distinct students present in last 30 days
    unique_monthly_present = (
        db.execute(
            select(func.count(func.distinct(AttendanceRecord.student_id_snapshot))).where(
                AttendanceRecord.attendance_date >= month_ago
            )
        ).scalar()
        or 0
    )

    monthly_rate = (
        min(100.0, round((unique_monthly_present / total_active) * 100.0, 1)) if total_active > 0 else 0.0
    )

    # Department totals & attendance in last 30 days
    dept_totals_rows = db.execute(
        select(
            Student.department,
            func.count(Student.id).label("total"),
        )
        .where(Student.status == "active", Student.deleted_at.is_(None))
        .group_by(Student.department)
    ).all()

    dept_totals: Dict[str, int] = {
        (row[0] or "Unassigned"): row[1] for row in dept_totals_rows
    }

    dept_presents_rows = db.execute(
        select(
            Student.department,
            func.count(func.distinct(AttendanceRecord.student_id_snapshot)).label("present"),
        )
        .join(Student, AttendanceRecord.student_id == Student.id)
        .where(
            AttendanceRecord.attendance_date >= month_ago,
            Student.status == "active",
            Student.deleted_at.is_(None),
        )
        .group_by(Student.department)
    ).all()

    dept_presents: Dict[str, int] = {
        (row[0] or "Unassigned"): row[1] for row in dept_presents_rows
    }

    department_stats = []
    for dept, total_count in dept_totals.items():
        present_count = dept_presents.get(dept, 0)
        rate = min(100.0, round((present_count / total_count) * 100.0, 1)) if total_count > 0 else 0.0
        department_stats.append(
            DepartmentStat(
                department=dept,
                total_students=total_count,
                present_today=present_count,
                attendance_rate=rate,
            )
        )
    department_stats.sort(key=lambda d: d.total_students, reverse=True)

    # 30-day daily trends
    trends_rows = db.execute(
        select(
            AttendanceRecord.attendance_date,
            func.count(AttendanceRecord.id),
            func.count(func.distinct(AttendanceRecord.student_id_snapshot)),
        )
        .where(AttendanceRecord.attendance_date >= month_ago)
        .group_by(AttendanceRecord.attendance_date)
        .order_by(AttendanceRecord.attendance_date.asc())
    ).all()

    daily_trends = [
        DailyTrendStat(
            date=row[0].isoformat(),
            attendance_count=row[1],
            unique_students=row[2],
        )
        for row in trends_rows
    ]

    return ReportsResponse(
        monthly_attendance_rate=monthly_rate,
        total_monthly_checkins=total_monthly,
        mean_confidence=mean_confidence,
        total_active_students=total_active,
        registered_face_templates=templates_count,
        departments=department_stats,
        daily_trends=daily_trends,
    )
