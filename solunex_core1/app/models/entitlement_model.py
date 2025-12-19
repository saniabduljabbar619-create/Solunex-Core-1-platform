from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Boolean
from datetime import datetime
from config import Base

class Entitlement(Base):
    __tablename__ = "entitlements"

    id = Column(Integer, primary_key=True, index=True)
    
    license_id = Column(Integer, ForeignKey("licenses.id"), nullable=False)
    service_id = Column(String(100), nullable=False)  # Admin, Cashier, Lab etc.
    
    total_allowed = Column(Integer, default=1, nullable=False)
    total_consumed = Column(Integer, default=0, nullable=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    is_active = Column(Boolean, default=True)
