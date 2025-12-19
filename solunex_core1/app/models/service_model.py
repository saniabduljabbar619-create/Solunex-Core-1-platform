# -*- coding: utf-8 -*-
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from datetime import datetime

from config import Base


class SystemService(Base):
    __tablename__ = "system_services"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, index=True)
    label = Column(String(150))
    status = Column(Boolean, default=True)            # enabled/disabled
    health = Column(String(20), default="online")     # online/offline/error
    last_check = Column(DateTime, default=datetime.utcnow)
    description = Column(Text, nullable=True)
    auto_restart = Column(Boolean, default=False)
