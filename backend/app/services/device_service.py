"""Device registration, telemetry, and API key lifecycle service."""

import secrets
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Device
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.utils.logger import logger


class DeviceService:
    """Manages edge camera devices, telemetry heartbeats, cryptographic credentials, and audio output."""

    # In-memory speaker state and audio queues
    _speaker_states: dict[str, bool] = {}  # device_code -> enabled
    _pending_pcm: dict[str, bytes] = {}     # device_code -> raw PCM bytes

    @staticmethod
    def generate_api_key() -> str:
        """Generates a secure random 32-character urlsafe API key."""
        return f"va_edge_{secrets.token_urlsafe(32)}"

    @staticmethod
    def hash_api_key(plain_key: str) -> str:
        """Hash a plaintext device API key using bcrypt."""
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(plain_key.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_api_key(plain_key: str, hashed_key: str) -> bool:
        """Constant-time bcrypt verification of device API key."""
        try:
            return bcrypt.checkpw(plain_key.encode("utf-8"), hashed_key.encode("utf-8"))
        except Exception:
            return False

    @classmethod
    def register_device(
        cls, db: Session, device_in: DeviceCreate
    ) -> Tuple[Device, str]:
        """
        Register a new edge device with hashed API credentials.
        Returns: (Device, plaintext_api_key)
        """
        plain_key = device_in.api_key if device_in.api_key else cls.generate_api_key()
        api_key_hash = cls.hash_api_key(plain_key)

        device = Device(
            device_name=device_in.device_name.strip(),
            device_code=device_in.device_code.strip(),
            api_key_hash=api_key_hash,
            location=device_in.location.strip() if device_in.location else None,
            is_active=True,
        )
        db.add(device)
        db.flush()
        logger.info(f"Registered edge device: {device.device_code} (UUID: {device.id})")
        return device, plain_key

    @classmethod
    def authenticate_device(
        cls, db: Session, device_code: str, plain_key: str
    ) -> Optional[Device]:
        """Authenticate an active edge device and update its last_seen_at timestamp."""
        stmt = select(Device).where(
            Device.device_code == device_code,
            Device.is_active.is_(True),
        )
        device = db.execute(stmt).scalar_one_or_none()

        if not device:
            return None

        if cls.verify_api_key(plain_key, device.api_key_hash):
            device.last_seen_at = datetime.now(timezone.utc)
            db.flush()
            return device

        return None

    @classmethod
    def rotate_device_key(
        cls, db: Session, device_id: uuid.UUID
    ) -> Optional[Tuple[Device, str]]:
        """
        Rotates the device API key and replaces the bcrypt hash.
        Returns: (Device, new_plain_key)
        """
        device = cls.get_by_id(db, device_id)
        if not device:
            return None

        new_plain_key = cls.generate_api_key()
        device.api_key_hash = cls.hash_api_key(new_plain_key)
        db.flush()
        logger.info(f"Rotated credentials for edge device: {device.device_code} ({device.id})")
        return device, new_plain_key

    @classmethod
    def update_device(
        cls, db: Session, device_id: uuid.UUID, update_in: DeviceUpdate
    ) -> Optional[Device]:
        """Update device metadata or active status."""
        device = cls.get_by_id(db, device_id)
        if not device:
            return None

        if update_in.device_name is not None:
            device.device_name = update_in.device_name.strip()
        if update_in.location is not None:
            device.location = update_in.location.strip() if update_in.location else None
        if update_in.is_active is not None:
            device.is_active = update_in.is_active

        db.flush()
        logger.info(f"Updated edge device: {device.device_code}")
        return device

    @classmethod
    def heartbeat(cls, db: Session, device_code: str) -> Optional[Device]:
        """Record telemetry heartbeat and update last_seen_at timestamp."""
        device = cls.get_by_code(db, device_code)
        if device and device.is_active:
            device.last_seen_at = datetime.now(timezone.utc)
            db.flush()
            return device
        return None

    @classmethod
    def delete_device(cls, db: Session, device_id: uuid.UUID) -> bool:
        """Deactivate edge device."""
        device = cls.get_by_id(db, device_id)
        if not device:
            return False

        device.is_active = False
        db.flush()
        logger.info(f"Deactivated edge device: {device.device_code} ({device.id})")
        return True

    @staticmethod
    def get_by_code(db: Session, device_code: str) -> Optional[Device]:
        stmt = select(Device).where(Device.device_code == device_code)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_id(db: Session, device_id: uuid.UUID) -> Optional[Device]:
        stmt = select(Device).where(Device.id == device_id)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def list_devices(
        db: Session, skip: int = 0, limit: int = 50
    ) -> Tuple[List[Device], int]:
        total = db.execute(select(func.count(Device.id))).scalar() or 0
        devices = (
            db.execute(select(Device).order_by(Device.created_at.desc()).offset(skip).limit(limit))
            .scalars()
            .all()
        )
        return list(devices), total

    @classmethod
    def get_speaker_state(cls, device_code: str) -> bool:
        return cls._speaker_states.get(device_code, True)

    @classmethod
    def set_speaker_state(cls, device_code: str, enabled: bool) -> bool:
        cls._speaker_states[device_code] = enabled
        logger.info(f"Speaker state for {device_code} set to: {'ENABLED' if enabled else 'MUTED'}")
        return enabled

    @classmethod
    def has_pending_audio(cls, device_code: str) -> bool:
        pcm = cls._pending_pcm.get(device_code)
        return bool(pcm and len(pcm) > 0)

    @classmethod
    def queue_pcm(cls, device_code: str, pcm_data: bytes) -> int:
        cls._pending_pcm[device_code] = pcm_data
        logger.info(f"Queued {len(pcm_data)} bytes of audio for {device_code}")
        return len(pcm_data)

    @classmethod
    def pop_pending_audio(cls, device_code: str) -> Optional[bytes]:
        pcm = cls._pending_pcm.pop(device_code, None)
        return pcm
