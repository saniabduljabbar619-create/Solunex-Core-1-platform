# -*- coding: utf-8 -*-
"""
APILog Model
-------------
Stores system and user action logs for tracking API activities,
user behavior, and debugging across the Solunex Core platform.
"""

from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from config import Base
import json


class APILog(Base):
    """
    Represents a record of any significant system or user event.
    Examples:
        - User login/logout
        - CRUD operations on database tables
        - API request/response tracking
        - System warnings or errors
    """

    __tablename__ = "logs"

    # Primary key
    id = Column(Integer, primary_key=True, index=True)

    # User or system agent responsible for the action
    user = Column(String(100), nullable=True)

    # Short descriptive title for the action
    action = Column(String(255), nullable=False)

    # Extended details or JSON describing the event
    details = Column(Text, nullable=True)

    # Optional IP address for tracking client origin
    ip_address = Column(String(50), nullable=True)

    # The API endpoint or route that triggered this event
    endpoint = Column(String(255), nullable=True)

    # Time when the event occurred
    timestamp = Column(DateTime, default=datetime.utcnow)


# ---------------------------------------------------------------
# Utility Function for Logging Events (FIXED + SAFE JSON HANDLING)
# ---------------------------------------------------------------

def log_event(db_session, user=None, action="", details=None, ip_address=None, endpoint=None):
    """
    Safe helper that stores a log record.
    FIX: Automatically serializes dict/list to JSON string.
    """

    # -----------------------------------------
    # 🔥 FIX: Convert dict/list → JSON string
    # -----------------------------------------
    if isinstance(details, (dict, list)):
        try:
            details = json.dumps(details, default=str)
        except Exception:
            details = str(details)
    elif details is not None:
        details = str(details)

    try:
        log_entry = APILog(
            user=user,
            action=action,
            details=details,
            ip_address=ip_address,
            endpoint=endpoint,
        )
        db_session.add(log_entry)
        db_session.commit()
        db_session.refresh(log_entry)
        return log_entry

    except Exception as e:
        db_session.rollback()
        print(f"[Log Error] Failed to store event: {e}")
        return None
