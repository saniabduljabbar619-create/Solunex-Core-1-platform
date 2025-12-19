from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from datetime import datetime
from config import Base

class AdminOverride(Base):
    __tablename__ = "admin_overrides"

    id = Column(Integer, primary_key=True, index=True)

    admin_email = Column(String(255), nullable=False)
    target_user_email = Column(String(255), nullable=False)
    license_key = Column(String(64), nullable=True)
    entitlement_id = Column(Integer, ForeignKey("entitlements.id"), nullable=True)
    installation_id = Column(Integer, ForeignKey("installations.id"), nullable=True)

    action_taken = Column(String(100), nullable=False)  # e.g., "revoked", "reassigned"
    reason = Column(Text, nullable=True)

    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(Text, nullable=True)
