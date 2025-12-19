# config.py
import urllib.parse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DB_USER = "solunex"
DB_PASS = "Health-focus@2025"
DB_HOST = "192.168.1.150"
DB_NAME = "solunex_core1"
DB_PORT = "3306"

encoded_pass = urllib.parse.quote_plus(DB_PASS)
SQLALCHEMY_DATABASE_URL = f"mysql+pymysql://{DB_USER}:{encoded_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

engine = create_engine(SQLALCHEMY_DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

JWT_SECRET = "b6d440de4fda11d73527c9f2a6fe295f225fb52b8c13852ff73c0f94bd20a8ac"  # or os.environ.get("JWT_SECRET")
JWT_ALGORITHM = "HS256"
ADMIN_USERNAME = "Abdoull"
LICENSE_API_KEY = "r03d814ec2e04c80dc9eb7bf2076d7907b2f1933a9909bee227dd472c531a2dda"  # or os.environ.get("LICENSE_API_KEY")


# config.py (add)
HMAC_SECRET = "1f8c4a41d42b6e7e219a02c9d257fbafc9b171f4a5d8b011bf4dc9a2f03d718a" # MUST set in environment for production
HMAC_TIMESTAMP_TOLERANCE = 15   # seconds (Option A)
HMAC_NONCE_TTL = 60             # seconds
HMAC_ALLOW_LOCAL_BYPASS = False # set True only for local dev if you must
REDIS_URL = None                # e.g. "redis://127.0.0.1:6379/0" or None to use in-memory nonce cache


# --------------------------------------------------------
# SMTP EMAIL CONFIG (NEEDED for license delivery emails)
# --------------------------------------------------------
SMTP_HOST = "smtp.gmail.com"       # Example: Gmail SMTP
SMTP_PORT = 587
SMTP_USER = "your_email@gmail.com"     # Your sender email
SMTP_PASS = "your-app-password"        # Use App Password for Gmail, not normal password
