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

    license_key = Column(String(64), unique=True, nullable=False, index=True)
    user_email = Column(String(255), nullable=False)

    # Primary app for backward compatibility
    primary_app_id = Column(String(100), nullable=True)

    status = Column(Enum(LicenseStatus), default=LicenseStatus.active, nullable=False)
    generated_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)
    last_verified = Column(DateTime, nullable=True)

    # Payment info
    order_id = Column(String(100), nullable=True)
    payment_reference = Column(String(100), nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String(10), default="USD", nullable=True)

    # Device & entitlement summary
    max_devices = Column(Integer, default=1)
    # bound devices → move to Installation table
    # bound_devices = Column(JSON, default=[]) # removed for platform clarity

    # Extra metadata
    meta = Column(JSON, default={})





