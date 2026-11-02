"""Attendance ledger query endpoints."""

import csv
import io
import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.security import verify_admin_key
from app.database.models import AttendanceRecord
from app.database.session import get_db
from app.schemas.attendance import AttendanceListResponse, AttendanceResponse
from app.schemas.common import ErrorResponse, SuccessResponse
from app.services.attendance_service import AttendanceService
from app.utils.logger import logger

router = APIRouter(prefix="/attendance", tags=["Attendance"])


def serialize_attendance(record: AttendanceRecord) -> AttendanceResponse:
    device_name = record.device.device_name if getattr(record, "device", None) else None
    device_code = record.device.device_code if getattr(record, "device", None) else None
    department = record.student.department if getattr(record, "student", None) else None
    return AttendanceResponse(
        id=record.id,
        student_id=record.student_id,
        student_id_snapshot=record.student_id_snapshot,
        student_name_snapshot=record.student_name_snapshot,
        attendance_date=record.attendance_date,
        check_in_time=record.check_in_time,
        device_id=record.device_id,
        recognition_confidence=record.recognition_confidence,
        recognition_method=record.recognition_method,
        status=record.status,
        device_name=device_name,
        device_code=device_code,
        department=department,
        created_at=record.created_at,
    )


@router.get(
    "",
    response_model=AttendanceListResponse,
    summary="List attendance records",
    description="Returns an immutable audit ledger of check-ins with date/student/device filters. Requires Admin Bearer Token.",
)
async def list_attendance(
    attendance_date: Optional[date] = Query(None, description="Filter by exact date (YYYY-MM-DD)"),
    start_date: Optional[date] = Query(None, description="Filter start date"),
    end_date: Optional[date] = Query(None, description="Filter end date"),
    search: Optional[str] = Query(None, description="Search by student ID or full name"),
    student_id: Optional[str] = Query(None, description="Filter by student ID"),
    device_id: Optional[uuid.UUID] = Query(None, description="Filter by device UUID"),
    department: Optional[str] = Query(None, description="Filter by academic department"),
    batch: Optional[str] = Query(None, description="Filter by batch"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    records, total = AttendanceService.list_attendance(
        db,
        date_filter=attendance_date,
        start_date=start_date,
        end_date=end_date,
        search=search,
        student_id_filter=student_id,
        device_id_filter=device_id,
        department=department,
        batch=batch,
        skip=skip,
        limit=limit,
    )

    return AttendanceListResponse(
        total=total,
        records=[serialize_attendance(r) for r in records],
    )


@router.get(
    "/export",
    summary="Export attendance records as CSV",
    description="Returns filtered attendance records as a downloadable CSV. Requires Admin Bearer Token.",
)
async def export_attendance_csv(
    attendance_date: Optional[date] = Query(None, description="Filter by exact date"),
    start_date: Optional[date] = Query(None, description="Filter start date"),
    end_date: Optional[date] = Query(None, description="Filter end date"),
    search: Optional[str] = Query(None, description="Search by student ID or name"),
    student_id: Optional[str] = Query(None, description="Filter by student ID"),
    device_id: Optional[uuid.UUID] = Query(None, description="Filter by device UUID"),
    department: Optional[str] = Query(None, description="Filter by department"),
    batch: Optional[str] = Query(None, description="Filter by batch"),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    records, _ = AttendanceService.list_attendance(
        db,
        date_filter=attendance_date,
        start_date=start_date,
        end_date=end_date,
        search=search,
        student_id_filter=student_id,
        device_id_filter=device_id,
        department=department,
        batch=batch,
        skip=0,
        limit=10000,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Record UUID",
        "Date",
        "Student ID",
        "Student Name",
        "Department",
        "Check-In Time",
        "Device Node",
        "Confidence Score",
        "Method",
        "Status",
    ])

    for r in records:
        dev_label = r.device.device_name if r.device else (str(r.device_id) if r.device_id else "Direct API")
        dept_label = r.student.department if r.student and r.student.department else "Unassigned"
        conf_str = f"{r.recognition_confidence:.4f}" if r.recognition_confidence is not None else "N/A"
        writer.writerow([
            str(r.id),
            r.attendance_date.isoformat(),
            r.student_id_snapshot,
            r.student_name_snapshot,
            dept_label,
            r.check_in_time.isoformat(),
            dev_label,
            conf_str,
            r.recognition_method,
            r.status,
        ])

    csv_data = output.getvalue()
    filename = f"attendance_audit_{date.today().isoformat()}.csv"
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-cache",
        },
    )


@router.get(
    "/{record_id}",
    response_model=AttendanceResponse,
    summary="Get attendance record by ID",
    description="Retrieve a single attendance record by UUID. Requires Admin Bearer Token.",
    responses={
        404: {"model": ErrorResponse, "description": "Attendance record not found"},
    }
)
async def get_attendance_record(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    record = AttendanceService.get_record_by_id(db, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance record '{record_id}' not found."
        )
    return serialize_attendance(record)


@router.delete(
    "/{record_id}",
    response_model=SuccessResponse,
    summary="Delete attendance record",
    description="Deletes an attendance check-in record so the student can be re-recognized on the camera today. Requires Admin Bearer Token.",
    responses={
        404: {"model": ErrorResponse, "description": "Attendance record not found"},
    }
)
async def delete_attendance_record(
    record_id: uuid.UUID,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    record = AttendanceService.delete_record(db, record_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance record '{record_id}' not found."
        )
    db.commit()

    # Broadcast event to connected frontend clients to auto-refresh without reload
    try:
        from app.core.events import event_manager
        await event_manager.broadcast_attendance_event({
            "event": "attendance_deleted",
            "attendance_id": str(record.id),
            "student_id": record.student_id_snapshot,
            "student_name": record.student_name_snapshot,
            "attendance_date": record.attendance_date.isoformat(),
        })
    except Exception as e:
        logger.warning(f"Failed to broadcast attendance_deleted event: {e}")

    return SuccessResponse(
        status="success",
        message=f"Attendance record for student '{record.student_name_snapshot}' ({record.student_id_snapshot}) removed. Student is eligible for new check-in today."
    )
