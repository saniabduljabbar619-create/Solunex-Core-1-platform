# app/models/license_model.py
# -*- coding: utf-8 -*-
from sqlalchemy import Column, Integer, String, DateTime, Float, Enum, Boolean, JSON
from datetime import datetime
from config import Base
import enum


class LicenseStatus(enum.Enum):
    active = "active"
    revoked = "revoked"
    expired = "expired"


class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)

    # License identity
    license_key = Column(String(64), unique=True, nullable=False, index=True)
    user_email = Column(String(255), nullable=False)
    app_id = Column(String(100), nullable=False)

    # Status
    status = Column(Enum(LicenseStatus), default=LicenseStatus.active, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_verified = Column(DateTime, nullable=True)

    # Payment data
    order_id = Column(String(100), nullable=True)
    payment_reference = Column(String(100), nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String(10), default="USD", nullable=True)

    # Device binding
    is_bound = Column(Boolean, default=False)
    max_devices = Column(Integer, default=1)
    bound_devices = Column(JSON, default=[])

    # Metadata (renamed from 'metadata' → valid name)
    meta = Column(JSON, default={})

    def __repr__(self):
        return f"<License {self.license_key} ({self.status.value}) for {self.user_email}>"