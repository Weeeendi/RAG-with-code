"""
Data-to-Retrieval Loop 实验室模块数据库初始化
使用独立数据库 data/labs.db，不影响主 metadata.db
"""

import sqlite3
import os
from datetime import datetime
from config import LABS_DB_PATH


def get_db_connection():
    """获取数据库连接"""
    os.makedirs(os.path.dirname(LABS_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(LABS_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_labs_schema():
    """初始化实验室模块数据库表"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. asset_registry: 文件资产管理
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS asset_registry (
            asset_id TEXT PRIMARY KEY,
            file_name TEXT NOT NULL,
            file_path TEXT UNIQUE NOT NULL,
            file_size INTEGER,
            md5_hash TEXT NOT NULL,
            sha256_hash TEXT NOT NULL,
            mime_type TEXT,
            category TEXT,
            status TEXT DEFAULT 'uploaded'
                CHECK(status IN ('uploaded','parsing','parsed','indexing','indexed','error')),
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,
            tags TEXT,
            security_level TEXT DEFAULT 'internal'
                CHECK(security_level IN ('public','internal','confidential','secret')),
            expiry_date TEXT,
            owner TEXT,
            notes TEXT,
            version INTEGER DEFAULT 1,
            parent_asset_id TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    ''')

    # 2. experiment_configs: 实验配置
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS experiment_configs (
            config_id TEXT PRIMARY KEY,
            config_name TEXT NOT NULL,
            description TEXT,
            chunk_size INTEGER DEFAULT 800
                CHECK(chunk_size IN (500, 800, 1000)),
            overlap_ratio REAL DEFAULT 0.15
                CHECK(overlap_ratio IN (0.10, 0.15)),
            splitter_type TEXT DEFAULT 'smart',
            embedding_model TEXT,
            vector_weight_bm25 REAL DEFAULT 1.0,
            vector_weight_tfidf REAL DEFAULT 1.0,
            vector_weight_faiss REAL DEFAULT 1.0,
            asset_ids TEXT,
            index_name TEXT,
            is_shadow INTEGER DEFAULT 0,
            status TEXT DEFAULT 'draft'
                CHECK(status IN ('draft','active','archived')),
            created_at TEXT,
            updated_at TEXT
        )
    ''')

    # index_versions: 索引版本管理
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

    # 3. ground_truth_sets: 测试问题集
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ground_truth_sets (
            set_id TEXT PRIMARY KEY,
            set_name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            question_count INTEGER DEFAULT 0,
            avg_difficulty REAL DEFAULT 1.0,
            created_by TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')

    # 4. ground_truth_questions: 问题
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ground_truth_questions (
            qa_id TEXT PRIMARY KEY,
            set_id TEXT NOT NULL,
            question TEXT NOT NULL,
            expected_answer TEXT,
            relevant_asset_ids TEXT,
            relevant_chunk_ids TEXT,
            difficulty INTEGER CHECK(difficulty BETWEEN 1 AND 5),
            source TEXT,
            created_at TEXT,
            FOREIGN KEY (set_id) REFERENCES ground_truth_sets(set_id)
        )
    ''')

    # 5. recall_evaluations: 评估结果
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recall_evaluations (
            eval_id TEXT PRIMARY KEY,
            config_id TEXT NOT NULL,
            set_id TEXT NOT NULL,
            question TEXT,
            retrieved_chunk_ids TEXT,
            expected_chunk_ids TEXT,
            hits INTEGER DEFAULT 0,
            hit_rate REAL,
            mrr REAL,
            score_distribution TEXT,
            k_value INTEGER DEFAULT 10,
            evaluated_at TEXT,
            FOREIGN KEY (config_id) REFERENCES experiment_configs(config_id),
            FOREIGN KEY (set_id) REFERENCES ground_truth_sets(set_id)
        )
    ''')

    # 6. asset_chunk_mapping: 分块溯源
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS asset_chunk_mapping (
            mapping_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL,
            chunk_id TEXT NOT NULL,
            chunk_index INTEGER,
            original_page_number INTEGER,
            original_line_start INTEGER,
            original_line_end INTEGER,
            original_bounding_box TEXT,
            chunk_preview TEXT,
            created_at TEXT,
            FOREIGN KEY (asset_id) REFERENCES asset_registry(asset_id)
        )
    ''')

    # 7. processing_tasks: 异步任务
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS processing_tasks (
            task_id TEXT PRIMARY KEY,
            task_type TEXT NOT NULL,
            asset_id TEXT,
            config_id TEXT,
            status TEXT DEFAULT 'pending'
                CHECK(status IN ('pending','running','completed','failed')),
            progress REAL DEFAULT 0.0,
            input_params TEXT,
            output_result TEXT,
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT,
            FOREIGN KEY (asset_id) REFERENCES asset_registry(asset_id),
            FOREIGN KEY (config_id) REFERENCES experiment_configs(config_id)
        )
    ''')

    # 创建索引
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_status ON asset_registry(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_asset_md5 ON asset_registry(md5_hash)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_config_status ON experiment_configs(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_config_shadow ON experiment_configs(is_shadow)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_gt_set ON ground_truth_questions(set_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_eval_config ON recall_evaluations(config_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mapping_asset ON asset_chunk_mapping(asset_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mapping_chunk ON asset_chunk_mapping(chunk_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_status ON processing_tasks(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_version_active ON index_versions(is_active)')

    conn.commit()
    conn.close()
    print(f"[Labs DB] Initialized at {LABS_DB_PATH}")


if __name__ == "__main__":
    init_labs_schema()
