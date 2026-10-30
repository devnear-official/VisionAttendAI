"""Attendance ledger query endpoints."""

import uuid
from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import verify_admin_key
from app.database.session import get_db
from app.schemas.attendance import AttendanceListResponse, AttendanceResponse
from app.schemas.common import ErrorResponse
from app.services.attendance_service import AttendanceService

router = APIRouter(prefix="/attendance", tags=["Attendance"])


@router.get(
    "",
    response_model=AttendanceListResponse,
    summary="List attendance records",
    description="Returns an immutable audit ledger of check-ins with date/student/device filters. Requires Admin Bearer Token.",
)
async def list_attendance(
    attendance_date: Optional[date] = Query(None, description="Filter by date (YYYY-MM-DD)"),
    student_id: Optional[str] = Query(None, description="Filter by student ID"),
    device_id: Optional[uuid.UUID] = Query(None, description="Filter by device UUID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    records, total = AttendanceService.list_attendance(
        db,
        date_filter=attendance_date,
        student_id_filter=student_id,
        device_id_filter=device_id,
        skip=skip,
        limit=limit,
    )

    return AttendanceListResponse(
        total=total,
        records=[AttendanceResponse.model_validate(r) for r in records],
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
    return AttendanceResponse.model_validate(record)
