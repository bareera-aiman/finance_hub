# Migration for part (c). Run it BEFORE starting the app:  python migrate_c.py
import os
import shutil
import sqlite3
from datetime import datetime
from config import basedir

DB_PATH = os.path.join(basedir, "finance.db")

backup = os.path.join(basedir, f"finance_backup_{datetime.now():%Y%m%d_%H%M%S}.db")
shutil.copy(DB_PATH, backup)                                  # 1) backup first
print("Backup saved:", os.path.basename(backup))

con = sqlite3.connect(DB_PATH)
existing = {row[1] for row in con.execute('PRAGMA table_info("holding")')}
if "asset_type" in existing:
    print("holding.asset_type: already there, skipped")
else:
    # Existing holdings were all stocks, so that is their default
    con.execute("ALTER TABLE holding ADD COLUMN asset_type VARCHAR(30) NOT NULL DEFAULT 'Stocks'")
    print("holding.asset_type: added")
con.commit()
con.close()