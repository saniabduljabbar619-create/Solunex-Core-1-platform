from config import SessionLocal
from app.models.service_model import SystemService

db = SessionLocal()

services = [
    ("license_engine", "License Issuance Engine", "Handles license creation and storage"),
    ("validation_engine", "License Validation Engine", "Validates license keys in client apps"),
    ("email_delivery", "Email Delivery Service", "Sends system emails & alerts"),
    ("announcement_center", "Announcement System", "Delivers admin announcements"),
    ("analytics_engine", "Analytics Engine", "Aggregates dashboard analytics"),
    ("logging_engine", "Logging Engine", "Tracks actions, API logs, and system events"),
]

for name, label, desc in services:
    exists = db.query(SystemService).filter(SystemService.name == name).first()
    if not exists:
        db.add(SystemService(name=name, label=label, description=desc))

db.commit()
db.close()

print("Seeded system services.")
