"""
Migration: Add index_versions table to existing labs.db
"""
import sqlite3
import os
from config import LABS_DB_PATH


def run_migration():
    """添加 index_versions 表"""
    if not os.path.exists(LABS_DB_PATH):
        print(f"Database {LABS_DB_PATH} does not exist, skipping migration")
        return

    conn = sqlite3.connect(LABS_DB_PATH)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='index_versions'
    """)
    if cursor.fetchone():
        print("Table index_versions already exists")
        conn.close()
        return

    # Create table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS index_versions (
            index_version_id TEXT PRIMARY KEY,
            index_name TEXT NOT NULL,
            config_id TEXT,
            faiss_index_path TEXT,
            total_vectors INTEGER,
            vector_dim INTEGER,
            is_active INTEGER DEFAULT 0,
            is_default INTEGER DEFAULT 0,
            created_at TEXT,
            activated_at TEXT,
            deactivated_at TEXT,
            FOREIGN KEY (config_id) REFERENCES experiment_configs(config_id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_version_active ON index_versions(is_active)')

    conn.commit()
    conn.close()
    print("Migration completed: added index_versions table")


if __name__ == "__main__":
    run_migration()
