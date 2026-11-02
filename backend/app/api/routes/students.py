"""Student profile management endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import verify_admin_key
from app.database.session import get_db
from app.schemas.common import ErrorResponse
from app.schemas.student import StudentCreate, StudentListResponse, StudentResponse, StudentUpdate
from app.services.student_service import StudentService

router = APIRouter(prefix="/students", tags=["Students"])


@router.post(
    "",
    response_model=StudentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create student profile",
    description="Registers a new student record without biometric templates. Requires Admin Bearer Token.",
    responses={
        400: {"model": ErrorResponse, "description": "Student ID already exists"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        403: {"model": ErrorResponse, "description": "Forbidden"},
    }
)
async def create_student(
    student_in: StudentCreate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    existing = StudentService.get_by_student_id(db, student_in.student_id, include_deleted=True)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Student ID '{student_in.student_id}' is already registered."
        )

    student = StudentService.create_student(db, student_in)
    db.commit()

    return StudentResponse(
        id=student.id,
        student_id=student.student_id,
        full_name=student.full_name,
        email=student.email,
        department=student.department,
        batch=student.batch,
        phone=student.phone,
        status=student.status,
        created_at=student.created_at,
        updated_at=student.updated_at,
        deleted_at=student.deleted_at,
        embeddings_count=0,
    )


@router.get(
    "",
    response_model=StudentListResponse,
    summary="List students",
    description="Returns a paginated list of active students. Requires Admin Bearer Token.",
)
async def list_students(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status_filter: Optional[str] = Query(None, pattern="^(active|inactive)$"),
    search: Optional[str] = Query(None, description="Search by student_id or full_name"),
    department: Optional[str] = Query(None, description="Filter by department"),
    batch: Optional[str] = Query(None, description="Filter by batch"),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    students, total = StudentService.list_students(
        db,
        skip=skip,
        limit=limit,
        status_filter=status_filter,
        search=search,
        department=department,
        batch=batch,
        include_deleted=False,
    )

    results = []
    for s in students:
        emb_count = StudentService.count_active_embeddings(db, s.id)
        att_count, last_att = StudentService.get_student_attendance_stats(db, s.student_id, s.id)
        results.append(
            StudentResponse(
                id=s.id,
                student_id=s.student_id,
                full_name=s.full_name,
                email=s.email,
                department=s.department,
                batch=s.batch,
                phone=s.phone,
                status=s.status,
                created_at=s.created_at,
                updated_at=s.updated_at,
                deleted_at=s.deleted_at,
                embeddings_count=emb_count,
                attendance_count=att_count,
                last_attendance_at=last_att,
            )
        )

    return StudentListResponse(total=total, students=results)


@router.get(
    "/{student_id}",
    response_model=StudentResponse,
    summary="Get student by ID",
    description="Retrieve student details by student_id string. Requires Admin Bearer Token.",
    responses={
        404: {"model": ErrorResponse, "description": "Student not found"},
    }
)
async def get_student(
    student_id: str,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    student = StudentService.get_by_student_id(db, student_id, include_deleted=False)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found."
        )

    emb_count = StudentService.count_active_embeddings(db, student.id)
    att_count, last_att = StudentService.get_student_attendance_stats(db, student.student_id, student.id)
    return StudentResponse(
        id=student.id,
        student_id=student.student_id,
        full_name=student.full_name,
        email=student.email,
        department=student.department,
        batch=student.batch,
        phone=student.phone,
        status=student.status,
        created_at=student.created_at,
        updated_at=student.updated_at,
        deleted_at=student.deleted_at,
        embeddings_count=emb_count,
        attendance_count=att_count,
        last_attendance_at=last_att,
    )


@router.patch(
    "/{student_id}",
    response_model=StudentResponse,
    summary="Update student profile",
    description="Update non-biometric student details. Requires Admin Bearer Token.",
    responses={
        404: {"model": ErrorResponse, "description": "Student not found"},
    }
)
async def update_student(
    student_id: str,
    update_in: StudentUpdate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    student = StudentService.update_student(db, student_id, update_in)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found."
        )
    db.commit()

    emb_count = StudentService.count_active_embeddings(db, student.id)
    att_count, last_att = StudentService.get_student_attendance_stats(db, student.student_id, student.id)
    return StudentResponse(
        id=student.id,
        student_id=student.student_id,
        full_name=student.full_name,
        email=student.email,
        department=student.department,
        batch=student.batch,
        phone=student.phone,
        status=student.status,
        created_at=student.created_at,
        updated_at=student.updated_at,
        deleted_at=student.deleted_at,
        embeddings_count=emb_count,
        attendance_count=att_count,
        last_attendance_at=last_att,
    )


@router.delete(
    "/{student_id}",
    response_model=StudentResponse,
    summary="Soft-delete student profile",
    description="Soft-deletes student record and deactivates face embeddings while preserving historical attendance.",
    responses={
        404: {"model": ErrorResponse, "description": "Student not found"},
    }
)
async def delete_student(
    student_id: str,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    student = StudentService.soft_delete_student(db, student_id)
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student '{student_id}' not found."
        )
    db.commit()

    emb_count = StudentService.count_active_embeddings(db, student.id)
    att_count, last_att = StudentService.get_student_attendance_stats(db, student.student_id, student.id)
    return StudentResponse(
        id=student.id,
        student_id=student.student_id,
        full_name=student.full_name,
        email=student.email,
        department=student.department,
        batch=student.batch,
        phone=student.phone,
        status=student.status,
        created_at=student.created_at,
        updated_at=student.updated_at,
        deleted_at=student.deleted_at,
        embeddings_count=emb_count,
        attendance_count=att_count,
        last_attendance_at=last_att,
    )
