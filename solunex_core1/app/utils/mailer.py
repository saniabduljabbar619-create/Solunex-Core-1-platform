# app/utils/mailer.py
import smtplib
from email.mime.text import MIMEText
from email.utils import formataddr

# -------------------------------------------------------
#  HARD-CODED GMAIL SMTP SETTINGS
#  (Because you are not using .env)
# -------------------------------------------------------
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "solunexcompany@gmail.com"          # your gmail
SMTP_PASS = "xqdb vucm mpds ijev"               # your app password
SENDER_NAME = "Solunex License System"

def send_email(to_email: str, subject: str, html_body: str):
    """
    Send Solunex HTML email through Gmail SMTP.
    """

    # force everything to str just in case
    to_email = str(to_email)
    subject = str(subject)
    html_body = str(html_body)

    msg = MIMEText(html_body, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = formataddr((SENDER_NAME, SMTP_USER))
    msg["To"] = to_email

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(SMTP_USER, [to_email], msg.as_string())

        print(f"📧 Email sent successfully to {to_email}")
        return True

    except Exception as e:
        print(f"❌ Email send error: {type(e)} {e}")
        return False
