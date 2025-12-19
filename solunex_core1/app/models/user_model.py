from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime
from config import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String(100), unique=True, nullable=False)
    username = Column(String(50), unique=True, nullable=True)

    password_hash = Column(String(255), nullable=False)

    role = Column(String(50), default="user")  # user, admin, support, super_admin
    is_active = Column(Boolean, default=True)

    last_login_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
