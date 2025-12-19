from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum, Boolean
from datetime import datetime
from config import Base
import enum

class InstallationStatus(enum.Enum):
    active = "active"
    revoked = "revoked"
    failed = "failed"

class Installation(Base):
    __tablename__ = "installations"

    id = Column(Integer, primary_key=True, index=True)
    
    license_id = Column(Integer, ForeignKey("licenses.id"), nullable=False)
    entitlement_id = Column(Integer, ForeignKey("entitlements.id"), nullable=False)
    
    device_uuid = Column(String(100), nullable=False)
    service_id = Column(String(100), nullable=False)
    
    status = Column(Enum(InstallationStatus), default=InstallationStatus.active, nullable=False)
    installed_at = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, nullable=True)
