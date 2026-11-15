import os
import secrets

# Folder where this file lives, so the database path works on any machine
basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Secret key signs the session cookie. It is read from an environment variable.
    # If the variable is missing (local testing only), a random key is generated,
    # so no secret is ever written in the code. Sessions reset on restart locally.
    SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    # SQLite database file stored next to the project
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + os.path.join(basedir, "finance.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True    # JavaScript cannot read the session cookie
    SESSION_COOKIE_SAMESITE = "Lax"   # cookie is not sent on cross-site POST requests
    # Send the session cookie only over HTTPS. Set SECURE_COOKIES=1 on the server (not on your laptop).
    SESSION_COOKIE_SECURE = os.environ.get("SECURE_COOKIES") == "1"
    UPI_ID = os.environ.get("UPI_ID")   # no default on purpose: your UPI ID must never be in the code
    UPI_PAYEE_NAME = os.environ.get("UPI_PAYEE_NAME", "FinanceHub Demo")