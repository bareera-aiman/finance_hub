# One-off migration for part (a). Run it BEFORE starting the app:  python migrate_a.py
import os
import shutil
import sqlite3
from datetime import datetime

from flask import Flask
from config import Config, basedir
from models import db

DB_PATH = os.path.join(basedir, "finance.db")

# table -> list of (new column, SQL definition). Existing rows automatically get the DEFAULT value.
NEW_COLUMNS = {
    "user": [
        ("opening_balance", "FLOAT NOT NULL DEFAULT 0"),
        ("plan", "VARCHAR(10) NOT NULL DEFAULT 'free'"),
        ("premium_until", "DATETIME"),
        ("is_admin", "BOOLEAN NOT NULL DEFAULT 0"),
    ],
    "expense": [
        ("payment_mode", "VARCHAR(20) NOT NULL DEFAULT 'Cash'"),
        ("child_id", "INTEGER REFERENCES child(id)"),
    ],
}


def main():
    # 1) Backup first, so you can always go back
    if os.path.exists(DB_PATH):
        backup = os.path.join(basedir, f"finance_backup_{datetime.now():%Y%m%d_%H%M%S}.db")
        shutil.copy(DB_PATH, backup)
        print("Backup saved:", os.path.basename(backup))
    else:
        print("No database found, so a fresh one will be created. Nothing to migrate.")

    # 2) Create any missing tables (child, payment_request). Existing tables are left untouched.
    #    We build a tiny app here instead of importing app.py, because importing app.py would
    #    query the old tables before they have the new columns.
    mini_app = Flask(__name__)
    mini_app.config.from_object(Config)
    db.init_app(mini_app)
    with mini_app.app_context():
        db.create_all()
    print("New tables ready.")

    # 3) Add the new columns to the existing tables (skip any that already exist)
    con = sqlite3.connect(DB_PATH)
    for table, columns in NEW_COLUMNS.items():
        existing = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
        for name, definition in columns:
            if name in existing:
                print(f"  {table}.{name}: already there, skipped")
            else:
                con.execute(f'ALTER TABLE "{table}" ADD COLUMN {name} {definition}')
                print(f"  {table}.{name}: added")
    con.commit()
    con.close()
    print("Migration finished. Your existing data is untouched.")


if __name__ == "__main__":
    main()