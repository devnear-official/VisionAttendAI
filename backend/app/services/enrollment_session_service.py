"""Edge device biometric enrollment session management service.

Architecture Note:
    This implementation currently uses an in-memory session store suitable for
    single-process FastAPI development and edge deployments. The storage interface
    is fully encapsulated within EnrollmentSessionService and IEnrollmentSessionStore,
    allowing drop-in replacement with Redis or PostgreSQL-backed persistence for
    multi-worker or distributed deployments without changing the API route contracts.
"""

import abc
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np

from app.utils.logger import logger


@dataclass
class EnrollmentSample:
    """Represents a validated face embedding sample collected during an enrollment session."""
    index: int
    embedding: np.ndarray
    quality_score: float
    captured_at: float = field(default_factory=time.time)


@dataclass
class EnrollmentSession:
    """Active biometric enrollment session data model."""
    session_id: str
    student_id: str
    name: str
    department: Optional[str]
    batch: Optional[str]
    device_code: str
    target_samples: int
    ttl_seconds: int = 120
    created_at: float = field(default_factory=time.time)
    status: str = "active"  # "active", "completed", "failed", "cancelled", "expired"
    error_message: Optional[str] = None
    samples: List[EnrollmentSample] = field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        if self.status != "active":
            return False
        return (time.time() - self.created_at) > self.ttl_seconds

    @property
    def expires_in_seconds(self) -> int:
        if self.status != "active":
            return 0
        remaining = int(self.ttl_seconds - (time.time() - self.created_at))
        return max(0, remaining)

    @property
    def collected_count(self) -> int:
        return len(self.samples)

    @property
    def is_target_reached(self) -> bool:
        return self.collected_count >= self.target_samples


class IEnrollmentSessionStore(abc.ABC):
    """Abstract storage interface for enrollment sessions."""

    @abc.abstractmethod
    def save(self, session: EnrollmentSession) -> None:
        pass

    @abc.abstractmethod
    def get(self, session_id: str) -> Optional[EnrollmentSession]:
        pass

    @abc.abstractmethod
    def get_by_device(self, device_code: str) -> Optional[EnrollmentSession]:
        pass

    @abc.abstractmethod
    def get_by_student(self, student_id: str) -> Optional[EnrollmentSession]:
        pass

    @abc.abstractmethod
    def remove(self, session_id: str) -> bool:
        pass

    @abc.abstractmethod
    def purge_expired(self) -> int:
        pass


class InMemoryEnrollmentSessionStore(IEnrollmentSessionStore):
    """
    Thread-safe in-memory session store.
    Notice: Session state is bound to the running Python process memory.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: Dict[str, EnrollmentSession] = {}

    def save(self, session: EnrollmentSession) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[EnrollmentSession]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session and session.is_expired:
                session.status = "expired"
            return session

    def get_by_device(self, device_code: str) -> Optional[EnrollmentSession]:
        with self._lock:
            for session in self._sessions.values():
                if session.device_code == device_code:
                    if session.is_expired:
                        session.status = "expired"
                    if session.status == "active":
                        return session
            return None

    def get_by_student(self, student_id: str) -> Optional[EnrollmentSession]:
        with self._lock:
            for session in self._sessions.values():
                if session.student_id == student_id:
                    if session.is_expired:
                        session.status = "expired"
                    if session.status == "active":
                        return session
            return None

    def remove(self, session_id: str) -> bool:
        with self._lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                return True
            return False

    def purge_expired(self) -> int:
        with self._lock:
            purged = 0
            now = time.time()
            to_delete = []
            for sid, sess in self._sessions.items():
                if sess.status == "active" and (now - sess.created_at) > sess.ttl_seconds:
                    sess.status = "expired"
                # Keep terminal sessions around briefly (5 mins) for UI queries, then purge
                if sess.status in ("completed", "failed", "cancelled", "expired") and (now - sess.created_at) > 300:
                    to_delete.append(sid)

            for sid in to_delete:
                del self._sessions[sid]
                purged += 1
            return purged


class EnrollmentSessionService:
    """High-level service coordinating edge device biometric enrollment sessions."""

    _store: IEnrollmentSessionStore = InMemoryEnrollmentSessionStore()

    @classmethod
    def set_store(cls, store: IEnrollmentSessionStore) -> None:
        """Allow injecting alternative storage backends (e.g. Redis)."""
        cls._store = store

    @classmethod
    def create_session(
        cls,
        student_id: str,
        name: str,
        department: Optional[str],
        batch: Optional[str],
        device_code: str,
        target_samples: int = 3,
        ttl_seconds: int = 120,
    ) -> EnrollmentSession:
        """
        Creates and starts a new edge biometric enrollment session.
        Prevents multiple active sessions on the same device or for the same student.
        """
        cls._store.purge_expired()

        clean_device = device_code.strip()
        clean_student = student_id.strip()

        # Check for existing active session on device
        existing_device_session = cls._store.get_by_device(clean_device)
        if existing_device_session and existing_device_session.status == "active":
            raise ValueError(
                f"Device '{clean_device}' is already engaged in an active enrollment session "
                f"for student '{existing_device_session.student_id}'. Cancel or wait for it to complete."
            )

        # Check for existing active session for student
        existing_student_session = cls._store.get_by_student(clean_student)
        if existing_student_session and existing_student_session.status == "active":
            raise ValueError(
                f"Student '{clean_student}' already has an active enrollment session on device "
                f"'{existing_student_session.device_code}'."
            )

        session_id = str(uuid.uuid4())
        session = EnrollmentSession(
            session_id=session_id,
            student_id=clean_student,
            name=name.strip(),
            department=department.strip() if department else None,
            batch=batch.strip() if batch else None,
            device_code=clean_device,
            target_samples=max(3, min(5, target_samples)),
            ttl_seconds=max(30, min(600, ttl_seconds)),
        )

        cls._store.save(session)
        logger.info(
            f"Created enrollment session {session_id} for student '{clean_student}' on device '{clean_device}' "
            f"target={session.target_samples} samples (TTL: {session.ttl_seconds}s)"
        )
        return session

    @classmethod
    def get_session(cls, session_id: str) -> Optional[EnrollmentSession]:
        cls._store.purge_expired()
        return cls._store.get(session_id)

    @classmethod
    def get_active_session_for_device(cls, device_code: str) -> Optional[EnrollmentSession]:
        cls._store.purge_expired()
        return cls._store.get_by_device(device_code.strip())

    @classmethod
    def cancel_session(cls, session_id: str) -> bool:
        session = cls.get_session(session_id)
        if not session:
            return False
        if session.status == "active":
            session.status = "cancelled"
            cls._store.save(session)
            logger.info(f"Cancelled enrollment session {session_id}")
            return True
        return False

    @classmethod
    def mark_completed(cls, session_id: str) -> None:
        """Mark an enrollment session as successfully committed to database."""
        session = cls.get_session(session_id)
        if session:
            session.status = "completed"
            session.error_message = None
            cls._store.save(session)
            logger.info(f"Marked enrollment session {session_id} as completed.")

    @classmethod
    def mark_failed(cls, session_id: str, error_msg: str) -> None:
        """Mark an enrollment session as failed due to database or validation errors."""
        session = cls.get_session(session_id)
        if session:
            session.status = "failed"
            session.error_message = error_msg
            cls._store.save(session)
            logger.error(f"Marked enrollment session {session_id} as failed: {error_msg}")

    @classmethod
    def add_sample(
        cls, session_id: str, embedding: np.ndarray, quality_score: float
    ) -> Tuple[EnrollmentSession, bool]:
        """
        Appends a validated 512-D embedding to the active session.
        Returns: (session, is_complete)
        """
        session = cls.get_session(session_id)
        if not session:
            raise ValueError("Enrollment session does not exist.")

        if session.status != "active":
            raise ValueError(f"Cannot add sample: session is in '{session.status}' state.")

        if session.is_expired:
            session.status = "expired"
            cls._store.save(session)
            raise ValueError("Enrollment session has expired.")

        new_index = len(session.samples) + 1
        sample = EnrollmentSample(
            index=new_index,
            embedding=embedding,
            quality_score=quality_score,
        )
        session.samples.append(sample)

        is_complete = session.is_target_reached
        cls._store.save(session)
        logger.info(
            f"Added sample {new_index}/{session.target_samples} to enrollment session {session_id} "
            f"(Score: {quality_score:.2f}, Complete: {is_complete})"
        )
        return session, is_complete
