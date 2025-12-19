from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Boolean
from datetime import datetime
from config import Base
import enum

class InstallerStatus(enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"
    revoked = "revoked"

class InstallerSession(Base):
    __tablename__ = "installer_sessions"

    id = Column(Integer, primary_key=True, index=True)

    # References
    user_email = Column(String(255), nullable=False)
    license_key = Column(String(64), nullable=False)
    entitlement_id = Column(Integer, ForeignKey("entitlements.id"), nullable=True)
    installation_id = Column(Integer, ForeignKey("installations.id"), nullable=True)

    # Device / Setup info
    device_uuid = Column(String(100), nullable=False)
    app_id = Column(String(100), nullable=False)
    exe_version = Column(String(20), nullable=True)

    status = Column(Enum(InstallerStatus), default=InstallerStatus.pending, nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime, nullable=True)
    ip_address = Column(String(50), nullable=True)

    # Extra details
    details = Column(String(255), nullable=True)
