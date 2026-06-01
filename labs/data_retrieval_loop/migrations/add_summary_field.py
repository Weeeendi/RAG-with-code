"""
Migration: Add summary field to asset_registry table
"""

import sqlite3
import os
from config import LABS_DB_PATH


def migrate():
    """添加summary字段到asset_registry表"""
    conn = sqlite3.connect(LABS_DB_PATH)
    cursor = conn.cursor()

    # 检查是否已有summary字段
    cursor.execute("PRAGMA table_info(asset_registry)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'summary' not in columns:
        cursor.execute("ALTER TABLE asset_registry ADD COLUMN summary TEXT")
        print("[Migration] Added 'summary' column to asset_registry")
    else:
        print("[Migration] 'summary' column already exists")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
