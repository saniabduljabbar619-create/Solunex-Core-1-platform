# -*- coding: utf-8 -*-
"""
Announcements API
-----------------
Allows the Solunex admin to broadcast announcements or updates
to all registered clients. Messages are sent asynchronously via email
and logged for analytics.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session
from config import SessionLocal
from app.models.license_model import License
from app.models.logs_model import APILog
from app.utils.mailer import send_email
from sqlalchemy import text

from datetime import datetime
import json

router = APIRouter(prefix="/admin", tags=["announcements"])

# -------------------------------------------------
# Database Dependency
# -------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------------------------------
# Schema
# -------------------------------------------------
class AnnouncementIn(BaseModel):
    title: str
    message: str
    category: str = "General"


# -------------------------------------------------
# Helper: Log Action
# -------------------------------------------------
def log_announcement(db: Session, title: str, message: str, recipients: int):
    try:
        entry = APILog(
            user="admin",
            action="announcement_sent",
            details=json.dumps({
                "title": title,
                "message": message,
                "recipients": recipients
            }),
            timestamp=datetime.utcnow()
        )
        db.add(entry)
        db.commit()
    except Exception:
        db.rollback()

# -------------------------------------------------
# Endpoint: Post Announcement
# -------------------------------------------------

from fastapi import Form
@router.post("/post_announcement")
def post_announcement(
        payload: AnnouncementIn,
        background: BackgroundTasks,
        db: Session = Depends(get_db)
):

    # fetch emails
    clients = db.execute(text("SELECT DISTINCT user_email FROM licenses")).fetchall()

    emails = []
    for c in clients:
        email = c[0]

        if not email:
            continue

        if isinstance(email, bytes):
            email = email.decode("utf-8", errors="ignore")

        emails.append(email)

    if not emails:
        raise HTTPException(status_code=404, detail="No clients found to send announcements.")

    def _send_all(title: str, message: str, category: str, recipients: list[str]):
        print("SEND EMAIL DEBUG >>>")
        # show how many recipients we will attempt to send to
        print("RECIPIENTS_COUNT:", len(recipients))

        # build subject and a template body so debug prints reference defined variables
        subject = f"[Solunex Update] {title}"
        template = f"""
            <h3>{title}</h3>
            <p><strong>Category:</strong> {category}</p>
            <br>
            <p>{message}</p>
            <br><hr>
            <small>Sent via Solunex Core Announcement Service</small>
            """

        # print a short preview of the body for debugging
        print("SUBJECT:", subject, type(subject))
        preview = (template[:120] + "...") if len(template) > 120 else template
        print("BODY_PREVIEW:", preview, type(preview))

        for e in recipients:
            body = template
            send_email(e, subject, body)

    background.add_task(_send_all, payload.title, payload.message, payload.category, emails)

    # log event
    log_announcement(db, payload.title, payload.message, len(emails))

    return {
        "status": "queued",
        "recipients": len(emails),
        "title": payload.title,
        "message": payload.message,
        "category": payload.category
    }
