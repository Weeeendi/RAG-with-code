import sqlite3
import os
import json
import re
import math
import jieba
import numpy as np
import faiss
from typing import List, Dict, Any, Optional, Set, Tuple
from datetime import datetime
from dataclasses import dataclass
from collections import Counter


CHINESE_TO_ENGLISH_MAP = {
    '时间': ['time', 'Time', 'TIME'],
    '同步': ['sync', 'Sync', 'SYNC', 'synchronize'],
    '获取': ['get', 'fetch', 'obtain', 'acquire'],
    '设备': ['device', 'Device', 'DEVICE'],
    '信息': ['info', 'information', 'Information'],
    '配对': ['pair', 'Pair', 'PAIR', 'pairing'],
    '绑定': ['bind', 'Bind', 'BIND', 'bond', 'Bond', 'BOND'],
    '解绑': ['unbind', 'Unbind', 'UNBIND'],
    '骑行': ['ride', 'Ride', 'RIDE', 'riding'],
    '记录': ['record', 'Record', 'RECORD', 'log'],
    '故障': ['fault', 'Fault', 'FAULT', 'error', 'Error', 'ERROR'],
    '电量': ['battery', 'Battery', 'BATTERY', 'power'],
    '电池': ['battery', 'Battery', 'BATTERY'],
    '升级': ['upgrade', 'Upgrade', 'UPGRADE', 'ota', 'OTA', 'update'],
    'BLE': ['ble', 'Ble', 'BLUETOOTH', 'bluetooth'],
    '上报': ['report', 'Report', 'REPORT', 'report'],
    '数据': ['data', 'Data', 'DATA', 'dp', 'DP'],
    'DP': ['dp', 'DP', 'data', 'Data', 'DATA'],
    'dp': ['dp', 'DP', 'data', 'Data', 'DATA'],
}


SYNONYM_DICT = {
    '同步': ['dp_query', '0x0003', 'APP_SYNC_TIME', '状态查询', '上报', '0x8003', '时间同步'],
    '获取': ['同步', '查询', '获取时间', '获取同步'],
    '获取时间': ['时间同步', '同步', 'APP_SYNC_TIME', '0x8003'],
    '时间信息': ['时间同步', '时间', 'APP_SYNC_TIME', '0x8003', '0x0025'],
    '骑行': ['record', '0x8005', 'record_reported', '骑行记录'],
    '生成': ['创建', '产生'],
    '数据': ['dp', 'DP', 'data'],
    'App': ['app', '应用程序'],
    '开机': ['启动', '开机电'],
    '指令': ['命令', 'can指令'],
    '仪表': ['车仪表', '车载仪表'],
    'CAN': ['can', 'CAN', '总线'],
    '状态查询': ['dp_query', '0x0003', '查询'],
    'BLE': ['ble', '蓝牙'],
    '上报': ['report', 'REPORT'],
    '报文': ['message', 'MSG', 'can报文'],
    'bluetooth': ['bluetooth', 'BLE', 'ble'],
    'record': ['record', '骑行', '骑行记录'],
    '0x8005': ['0x8005', 'record_reported', 'RECORD_REPORTED', '骑行记录', 'RECORD_REPORT', '记录帧'],
    '骑行记录': ['record', '0x8005', 'record_reported', '骑行', '生成记录', '记录上报'],
    'dp_query': ['dp_query', 'DP_QUERY', '状态查询', '0x0003'],
    '报错': ['fault', 'error', 'alarm', 'detection', '故障', '异常', '错误'],
    '故障': ['fault', 'alarm', 'rollover', 'detection', 'FAULT', 'ALARM', '报错', '异常'],
    '错误': ['error', 'fault', 'err', 'ERROR', '异常'],
    'riding': ['骑行', 'record', '骑行记录'],
    'battery': ['电量', '电池', 'battery_percentage'],
    'fault': ['故障', 'alarm', '错误'],
    'OTA': ['升级', 'ota'],
    '时间': ['time', '时间同步', 'APP_SYNC_TIME', '0x8003', '0x0025'],
    '0x8003': ['0x8003', 'APP_SYNC_TIME', '时间同步', 'SYNC_TIME', '时间帧', '同步时间'],
    '配对': ['pair', 'pairing', 'bond', '绑定'],
    '绑定': ['bond', 'bonding', 'bind', '配对'],
    '解绑': ['unbind', '解绑请求', 'DEVICE_UNBIND'],
    '帧格式': ['frame', '帧格式', '帧结构', 'CMD', '0x8003', '0x8005'],
    'HID': ['hid', 'HID', '人机接口'],
    'BMS': ['bms', 'BMS', '电池管理'],
    '电量': ['battery', '电池', '电量百分比', 'battery_percentage'],
    '充电': ['charge', '充电', '充电器'],
    '故障检测': ['fault', 'alarm', '检测', 'rollover', '碰撞', '震动'],
    'rollover': ['翻车', 'rollover', '倾倒'],
    '震动': ['vibration', '震动', '震动报警'],
    '碰撞': ['collision', '碰撞', 'collide'],
}


TECH_TERMS = {
    '骑行': ['record', '0x8005', 'record_reported', 'vl_ble'],
    '同步': ['dp_query', '0x0003', 'APP_SYNC_TIME', 'BLE', 'sync', '0x8003', '时间同步'],
    'App': ['app', 'ble', 'vl_app'],
    '开机': ['power', 'boot', 'start', 'iot'],
    'CAN': ['CAN', 'can', 'vl_can'],
    '指令': ['cmd', 'command', 'frame', 'ota'],
    '骑行记录': ['record', '0x8005', 'record_reported', 'vl_ble_record'],
    '同步数据': ['dp', 'data', 'sync', 'dp_query'],
    '状态查询': ['dp_query', '0x0003', 'query', 'status'],
    '报错机制': ['fault', 'alarm', 'detection', 'fault_param', 'rollover_detect'],
    '故障检测': ['fault', 'alarm', 'FAULT_TYPE', 'DPID_FAULT_DETECTION', 'rollover'],
    '错误处理': ['error', 'fault', 'err', 'mbedtls_err', 'ERROR_CODE'],
    'riding': ['骑行', 'record', '0x8005', '骑行记录'],
    'fault': ['故障', 'alarm', 'rollover', 'FAULT_TYPE'],
    'OTA': ['升级', 'ota', 'OTA_START', '固件', 'ota_upgrade'],
    'battery': ['电量', '电池', 'BMS', 'battery_percentage'],
    '时间同步': ['time_sync', 'APP_SYNC_TIME', '0x8003', '0x0025'],
    '配对绑定': ['pair', 'bond', 'bind', 'HID_pair', 'BLE_pair'],
    '帧格式': ['frame_format', '帧格式', '帧结构', 'CMD:'],
}


class QueryExpander:
    def __init__(self):
        self.synonym_dict = SYNONYM_DICT
        self.tech_terms = TECH_TERMS

    def expand(self, query: str) -> List[str]:
        import re
        query_lower = query.lower()
        expanded = {query_lower}

        english_tokens = re.findall(r'[a-zA-Z0-9_]+', query_lower)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', query_lower)
        chinese_bigrams = [chinese_chars[i] + chinese_chars[i+1] for i in range(len(chinese_chars)-1)]
        all_tokens = set(english_tokens) | set(chinese_bigrams)

        hex_pattern = re.compile(r'^(0x)?([0-9a-fA-F]+)$')
        for token in english_tokens:
            expanded.add(token)

            hex_match = hex_pattern.match(token)
            if hex_match:
                hex_val = hex_match.group(2)
                if len(hex_val) >= 2:
                    expanded.add(f"0x{hex_val}")
                    expanded.add(f"{token}")


            if token in self.synonym_dict:
                for syn in self.synonym_dict[token][:6]:
                    expanded.add(f"{query_lower} {syn}")
            if token in self.tech_terms:
                for term in self.tech_terms[token][:6]:
                    expanded.add(f"{query_lower} {term}")

            if token.lower() in ['dp', 'data', 'report', 'query']:
                for variant in ['dp', 'DP', 'data', 'Data', 'DATA', 'report', 'Report', 'REPORT']:
                    if variant != token:
                        expanded.add(query_lower.replace(token, variant))

        for bigram in chinese_bigrams:
            expanded.add(bigram)
            if bigram in CHINESE_TO_ENGLISH_MAP:
                for eng in CHINESE_TO_ENGLISH_MAP[bigram][:4]:
                    expanded.add(f"{query_lower} {eng}")
            if bigram in self.synonym_dict:
                for syn in self.synonym_dict[bigram][:4]:
                    expanded.add(f"{query_lower} {syn}")

        for eng_token in english_tokens:
            if eng_token in CHINESE_TO_ENGLISH_MAP:
                for ch in CHINESE_TO_ENGLISH_MAP[eng_token][:3]:
                    expanded.add(ch)
                    expanded.add(f"{query_lower} {ch}")

        if 'dp' in query_lower or '数据' in query_lower or '上报' in query_lower:
            for suffix in ['0x8001', '0x8003', '0x8005', '0x0003', 'dp_query', 'DP_QUERY', 'DP', 'dp', 'report', 'REPORT']:
                if suffix.lower() not in query_lower:
                    expanded.add(f"{query_lower} {suffix}")

        result = list(expanded)
        result.sort(key=lambda x: (0 if x == query_lower else 1, 0 if x.startswith(query_lower) else 1, -len(x)))
        return result[:20]

    def expand_structured(self, query: str) -> Dict[str, List[str]]:
        import re
        query_lower = query.lower()

        english_tokens = re.findall(r'[a-zA-Z0-9_]+', query_lower)
        chinese_chars = re.findall(r'[\u4e00-\uffff]', query_lower)
        chinese_bigrams = [chinese_chars[i] + chinese_chars[i+1] for i in range(len(chinese_chars)-1)]


        entities = []
        actions = []

        for token in english_tokens:
            if token in self.tech_terms:
                entities.append(token)
            if token in ['report', 'query', 'sync', 'get', 'set']:
                actions.append(token)

        for bigram in chinese_bigrams:
            if bigram in SYNONYM_DICT:
                syns = SYNONYM_DICT[bigram][:4]
                for syn in syns:
                    if any(s in ['report', 'query', '同步', '查询', '上报'] for s in [syn]):
                        actions.append(syn)
                    entities.append(syn)

        intent_patterns = ['怎么办', '如何', '怎么', '为什么', '什么时候']
        for pattern in intent_patterns:
            if pattern in query:
                for action in ['策略', '建议', '处理', '解决', '方案', '原因', '时间点']:
                    actions.append(action)

        return {
            'entities': list(set(entities))[:10],
            'actions': list(set(actions))[:10],
            'original': query_lower
        }

    def build_structured_query(self, query: str) -> str:
        structured = self.expand_structured(query)
        entities = structured['entities']
        actions = structured['actions']

        if not entities and not actions:
            return query

        or_groups = []

        if entities:
            or_groups.append(' OR '.join(entities))
        if actions:
            or_groups.append(' OR '.join(actions))

        return ' AND '.join(or_groups)


class QuestionTypeClassifier:
    QUESTION_PATTERNS = {
        'how': ['如何', '怎么', '怎样', '方法', '步骤', '实现', '生成'],
        'when': ['什么时候', '何时', '什么情况', '条件', '场景', '情况下'],
        'what': ['什么', '哪个', '哪些', '哪个'],
        'why': ['为什么', '原因'],
    }

    def classify(self, query: str) -> str:
        for qtype, keywords in self.QUESTION_PATTERNS.items():
            for kw in keywords:
                if kw in query:
                    return qtype
        return 'what'


@dataclass
class KnowledgeItem:
    id: str
    type: str
    category: str
    title: str
    content: str
    source_file: str
    line_number: int
    created_at: str
    metadata: Optional[Dict[str, Any]] = None
    parent_id: Optional[str] = None
    year: Optional[int] = None
    version: Optional[str] = None


class MetadataDB:
    def __init__(self, db_path: str = "data/metadata.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS knowledge_items (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source_file TEXT,
                    line_number INTEGER,
                    created_at TEXT NOT NULL,
                    metadata TEXT,
                    is_vectorized INTEGER DEFAULT 0,
                    parent_id TEXT,
                    year INTEGER,
                    version TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    is_resolved INTEGER DEFAULT 0,
                    suggested_content TEXT,
                    created_at TEXT NOT NULL,
                    resolved_at TEXT
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS file_vectors (
                    file_path TEXT PRIMARY KEY,
                    content_hash TEXT NOT NULL,
                    vector_data TEXT NOT NULL,
                    doc_count INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                )
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_category ON knowledge_items(category)
            ''')
            conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_source ON knowledge_items(source_file)
            ''')

            for col, col_type in [('parent_id', 'TEXT'), ('year', 'INTEGER'), ('version', 'TEXT')]:
                try:
                    conn.execute(f'ALTER TABLE knowledge_items ADD COLUMN {col} {col_type}')
                except sqlite3.OperationalError:
                    pass

            try:
                conn.execute('CREATE INDEX IF NOT EXISTS idx_year ON knowledge_items(year)')
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute('CREATE INDEX IF NOT EXISTS idx_parent ON knowledge_items(parent_id)')
            except sqlite3.OperationalError:
                pass

            # Content bigram index table for fast Chinese content lookup
            conn.execute('''
                CREATE TABLE IF NOT EXISTS content_bigram_index (
                    bigram TEXT,
                    file_path TEXT,
                    PRIMARY KEY (bigram, file_path)
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_bigram ON content_bigram_index(bigram)')

            # FTS5 virtual table for full-text search
            # Only create if doesn't exist (don't drop on every init)
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='content_fts'"
            )
            if not cursor.fetchone():
                conn.execute('''
                    CREATE VIRTUAL TABLE content_fts USING fts5(
                        file_path,
                        content,
                        tokenize="unicode61"
                    )
                ''')

    def build_content_bigram_index(self):
        """从现有knowledge_items构建content bigram索引"""
        import re
        with sqlite3.connect(self.db_path) as conn:
            # 清空旧索引
            conn.execute('DELETE FROM content_bigram_index')

            # 获取所有文件及其内容
            cursor = conn.execute('''
                SELECT DISTINCT source_file, content FROM knowledge_items
                WHERE content IS NOT NULL AND content != ''
            ''')

            entries = []
            file_count = 0
            for file_path, content in cursor:
                if not content:
                    continue
                file_count += 1
                # 提取中文bigrams
                chinese_chars = re.findall(r'[一-鿿]', content.lower())
                bigrams = set()
                for i in range(len(chinese_chars) - 1):
                    bigrams.add(chinese_chars[i] + chinese_chars[i+1])

                for bg in bigrams:
                    entries.append((bg, file_path))

            # 批量插入
            if entries:
                conn.executemany(
                    'INSERT OR IGNORE INTO content_bigram_index (bigram, file_path) VALUES (?, ?)',
                    entries
                )
            conn.commit()
            print(f"[BigramIndex] Built index with {len(entries)} entries from {file_count} files")

    def get_files_with_chinese_bigrams(self, bigrams: List[str]) -> List[str]:
        """根据中文bigrams查询包含这些内容的文件"""
        if not bigrams:
            return []
        placeholders = ','.join('?' * len(bigrams))
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(f'''
                SELECT DISTINCT file_path FROM content_bigram_index
                WHERE bigram IN ({placeholders})
            ''', bigrams)
            return [row[0] for row in cursor]

    def build_content_fts_index(self):
        """构建FTS5全文搜索索引"""
        with sqlite3.connect(self.db_path) as conn:
            # 清空旧索引
            conn.execute('DELETE FROM content_fts')

            # 按文件聚合所有内容
            cursor = conn.execute('''
                SELECT source_file, GROUP_CONCAT(content, ' ') as full_content
                FROM knowledge_items
                WHERE content IS NOT NULL AND content != '' AND source_file IS NOT NULL
                GROUP BY source_file
            ''')

            entries = []
            for file_path, content in cursor:
                if content and file_path:
                    entries.append((file_path, content))

            # 批量插入
            if entries:
                conn.executemany(
                    'INSERT INTO content_fts (file_path, content) VALUES (?, ?)',
                    entries
                )
            conn.commit()
            print(f"[FTS5] Built index with {len(entries)} files")

    def search_fts(self, query: str) -> List[str]:
        """使用FTS5进行全文搜索，返回匹配的文件路径"""
        if not query or not query.strip():
            return []
        with sqlite3.connect(self.db_path) as conn:
            try:
                # 构造FTS5 MATCH查询
                # 对于中文，将连续的中文字符串拆分为单个字符+bigram组合
                # 这样可以提高召回率（即使部分匹配也能找到）
                import re

                fts_queries = []

                # 分割混合字符串为单独token（按ASCII/非ASCII边界）
                tokens = re.findall(r'[A-Za-z0-9_]+|[^\sA-Za-z0-9_]+', query)

                for token in tokens:
                    if re.search(r'[一-鿿]', token):
                        # 中文token：拆分为单个字符和2-gram及以上组合
                        # 例如 "骑行记录" -> "骑*" OR "行*" OR "记*" OR "录*" OR "骑行*" OR "行记录*" ...
                        chars = list(token)
                        for i in range(len(chars)):
                            fts_queries.append(f'{chars[i]}*')
                        for n in range(2, min(len(chars) + 1, 5)):
                            for i in range(len(chars) - n + 1):
                                fts_queries.append(''.join(chars[i:i+n]) + '*')
                    else:
                        # 英文token，使用前缀匹配
                        fts_queries.append(f'{token}*')

                fts_query = ' OR '.join(fts_queries)
                cursor = conn.execute(f'''
                    SELECT file_path FROM content_fts
                    WHERE content MATCH '{fts_query}'
                ''')
                return [row[0] for row in cursor]
            except Exception as e:
                print(f"[FTS5] Search error: {e}")
                return []

    def insert_item(self, item: KnowledgeItem) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO knowledge_items
                    (id, type, category, title, content, source_file, line_number, created_at, metadata, is_vectorized, parent_id, year, version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
                ''', (
                    item.id, item.type, item.category, item.title,
                    item.content, item.source_file, item.line_number,
                    item.created_at, str(item.metadata) if item.metadata else None,
                    getattr(item, 'parent_id', None),
                    getattr(item, 'year', None),
                    getattr(item, 'version', None)
                ))
            return True
        except Exception as e:
            print(f"Error inserting item: {e}")
            return False

    def insert_items_batch(self, items: List[KnowledgeItem]) -> int:
        count = 0
        for item in items:
            if self.insert_item(item):
                count += 1
        return count

    def update_item(self, item_id: str, content: str = None, title: str = None,
                    metadata: Dict[str, Any] = None) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                updates = []
                params = []
                if content is not None:
                    updates.append("content = ?")
                    params.append(content)
                if title is not None:
                    updates.append("title = ?")
                    params.append(title)
                if metadata is not None:
                    updates.append("metadata = ?")
                    params.append(str(metadata))

                if not updates:
                    return False

                updates.append("is_vectorized = 0")
                params.append(item_id)

                conn.execute(f'''
                    UPDATE knowledge_items SET {', '.join(updates)}
                    WHERE id = ?
                ''', params)
            return True
        except Exception as e:
            print(f"Error updating item: {e}")
            return False

    def delete_item(self, item_id: str) -> bool:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM knowledge_items WHERE id = ?', (item_id,))
            return True
        except Exception as e:
            print(f"Error deleting item: {e}")
            return False

    def search_items_by_content(self, keyword: str, limit: int = 10, year: int = None, version: str = None, parent_id: str = None, category: str = None) -> List[KnowledgeItem]:
        items = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = '''
                SELECT * FROM knowledge_items
                WHERE (content LIKE ? OR title LIKE ?)
            '''
            params = [f'%{keyword}%', f'%{keyword}%']

            if category is not None:
                query += ' AND category = ?'
                params.append(category)
            if year is not None:
                query += ' AND year = ?'
                params.append(year)
            if version is not None:
                query += ' AND version = ?'
                params.append(version)
            if parent_id is not None:
                query += ' AND parent_id = ?'
                params.append(parent_id)

            query += ' LIMIT ?'
            params.append(limit)


            cursor = conn.execute(query, params)
            for row in cursor:
                items.append(KnowledgeItem(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    title=row['title'],
                    content=row['content'],
                    source_file=row['source_file'],
                    line_number=row['line_number'],
                    created_at=row['created_at'],
                    metadata=eval(row['metadata']) if row['metadata'] else None,
                    parent_id=row['parent_id'],
                    year=row['year'],
                    version=row['version']
                ))
        return items

    def get_parent_document(self, item_id: str) -> Optional[KnowledgeItem]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM knowledge_items WHERE id = ?
            ''', (item_id,))
            row = cursor.fetchone()
            if not row:
                return None
            parent_id = row['parent_id']
            if not parent_id:
                return None
            cursor = conn.execute('''
                SELECT * FROM knowledge_items WHERE id = ?
            ''', (parent_id,))
            row = cursor.fetchone()
            if row:
                return KnowledgeItem(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    title=row['title'],
                    content=row['content'],
                    source_file=row['source_file'],
                    line_number=row['line_number'],
                    created_at=row['created_at'],
                    metadata=eval(row['metadata']) if row['metadata'] else None,
                    parent_id=row['parent_id'],
                    year=row['year'],
                    version=row['version']
                )
            return None

    def mark_vectorized(self, item_ids: List[str]):
        with sqlite3.connect(self.db_path) as conn:
            placeholders = ','.join('?' * len(item_ids)) if item_ids else '""'
            conn.execute(f'''
                UPDATE knowledge_items SET is_vectorized = 1
                WHERE id IN ({placeholders})
            ''', item_ids)

    def get_items_by_file(self, file_path: str) -> List[KnowledgeItem]:
        items = []
        # Normalize path separators for cross-platform compatibility
        normalized_path = file_path.replace('\\', '/')
        basename = normalized_path.split('/')[-1]
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM knowledge_items WHERE source_file = ? OR source_file LIKE ?
            ''', (normalized_path, f'%{basename}'))
            for row in cursor:
                items.append(KnowledgeItem(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    title=row['title'],
                    content=row['content'],
                    source_file=row['source_file'],
                    line_number=row['line_number'],
                    created_at=row['created_at'],
                    metadata=eval(row['metadata']) if row['metadata'] else None,
                    parent_id=row['parent_id'],
                    year=row['year'],
                    version=row['version']
                ))
        return items

    def get_all_files(self) -> Set[str]:
        if hasattr(self, '_cached_files'):
            return self._cached_files
        files = set()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT DISTINCT source_file FROM knowledge_items')
            for row in cursor:
                if row[0]:
                    files.add(row[0])
        self._cached_files = files
        return files

    def get_files_by_category(self, category: str) -> List[str]:
        cache_key = f'_cached_files_{category}'
        if hasattr(self, cache_key):
            return getattr(self, cache_key)
        files = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT DISTINCT source_file FROM knowledge_items WHERE category = ?', (category,))
            for row in cursor:
                if row[0]:
                    files.append(row[0])
        setattr(self, cache_key, files)
        return files

    def get_vectorized_files(self) -> Dict[str, str]:
        files = {}
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT file_path, content_hash FROM file_vectors')
            for row in cursor:
                files[row[0]] = row[1]
        return files

    def save_file_vectors(self, file_path: str, content_hash: str, vector_data: str, doc_count: int):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO file_vectors (file_path, content_hash, vector_data, doc_count, updated_at)
                VALUES (?, ?, ?, ?, ?)
            ''', (file_path, content_hash, vector_data, doc_count, datetime.now().isoformat()))

    def get_file_vectors(self, file_path: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT vector_data FROM file_vectors WHERE file_path = ?', (file_path,))
            row = cursor.fetchone()
            return row[0] if row else None

    def add_feedback(self, question: str, answer: str, is_resolved: bool = False) -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO feedback (question, answer, is_resolved, created_at)
                VALUES (?, ?, ?, ?)
            ''', (question, answer, 1 if is_resolved else 0, datetime.now().isoformat()))
            return cursor.lastrowid

    def resolve_feedback(self, feedback_id: int, suggested_content: str = None):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                UPDATE feedback
                SET is_resolved = 1, resolved_at = ?, suggested_content = ?
                WHERE id = ?
            ''', (datetime.now().isoformat(), suggested_content, feedback_id))

    def get_unresolved_feedback(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute('''
                SELECT * FROM feedback WHERE is_resolved = 0 ORDER BY created_at DESC
            ''')
            return [dict(row) for row in cursor]

    def search_by_category(self, category: str, limit: int = 50, year: int = None) -> List[KnowledgeItem]:
        items = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = 'SELECT * FROM knowledge_items WHERE category = ?'
            params = [category]
            if year is not None:
                query += ' AND year = ?'
                params.append(year)
            query += ' LIMIT ?'
            params.append(limit)
            cursor = conn.execute(query, params)
            for row in cursor:
                items.append(KnowledgeItem(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    title=row['title'],
                    content=row['content'],
                    source_file=row['source_file'],
                    line_number=row['line_number'],
                    created_at=row['created_at'],
                    metadata=eval(row['metadata']) if row['metadata'] else None,
                    parent_id=row['parent_id'],
                    year=row['year'],
                    version=row['version']
                ))
        return items

    def search_items(self, item_ids: List[str]) -> List[KnowledgeItem]:
        if not item_ids:
            return []
        items = []
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ','.join('?' * len(item_ids))
            cursor = conn.execute(f'SELECT * FROM knowledge_items WHERE id IN ({placeholders})', item_ids)
            for row in cursor:
                items.append(KnowledgeItem(
                    id=row['id'],
                    type=row['type'],
                    category=row['category'],
                    title=row['title'],
                    content=row['content'],
                    source_file=row['source_file'],
                    line_number=row['line_number'],
                    created_at=row['created_at'],
                    metadata=eval(row['metadata']) if row['metadata'] else None,
                    parent_id=row['parent_id'],
                    year=row['year'],
                    version=row['version']
                ))
        return items


class SimpleTfidf:
    def __init__(self, max_features: int = 2000):
        self.max_features = max_features
        self.vocab = {}
        self.idf = []

    def _tokenize(self, text: str) -> list:
        text = text.lower()
        english_words = re.findall(r'[a-z0-9_]+', text)
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        chinese_bigrams = [chinese_chars[i]+chinese_chars[i+1] for i in range(len(chinese_chars)-1)]
        return english_words + chinese_bigrams

    def fit(self, documents: list) -> None:
        doc_count = len(documents)
        if doc_count == 0:
            return

        tokenized = [self._tokenize(doc) for doc in documents]
        all_tokens = [t for doc in tokenized for t in doc]
        token_counts = Counter(all_tokens)

        self.vocab = {t: i for i, (t, c) in enumerate(token_counts.most_common(self.max_features))}

        df = Counter()
        for doc_tokens in tokenized:
            unique_tokens = set(doc_tokens)
            for t in unique_tokens:
                if t in self.vocab:
                    df[t] += 1

        self.idf = [0] * len(self.vocab)
        for token, idx in self.vocab.items():
            self.idf[idx] = math.log((doc_count + 1) / (df.get(token, 0) + 1)) + 1

    def transform(self, documents: list) -> list:
        if not documents or not self.vocab:
            return []

        vectors = []
        for doc in documents:
            doc_tokens = self._tokenize(doc)
            tf = Counter(doc_tokens)
            vec = [0] * len(self.vocab)
            doc_len = len(doc_tokens) if doc_tokens else 1

            for token, count in tf.items():
                if token in self.vocab:
                    idx = self.vocab[token]
                    tf_val = count / doc_len
                    vec[idx] = tf_val * self.idf[idx]

            magnitude = math.sqrt(sum(v * v for v in vec))
            if magnitude > 0:
                vec = [v / magnitude for v in vec]
            vectors.append(vec)

        return vectors

    def fit_transform(self, documents: list) -> list:
        self.fit(documents)
        return self.transform(documents)

    def query(self, query: str) -> list:
        return self.transform([query])[0] if self.vocab else [0] * len(self.vocab)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[int, float]]:
        query_vec = self.transform([query])[0]
        if not query_vec:
            return []
        scores = []
        for i, doc_vec in enumerate(self.doc_vectors if hasattr(self, 'doc_vectors') else []):
            similarity = sum(q * d for q, d in zip(query_vec, doc_vec))
            scores.append((i, similarity))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores[:top_k]

    def fit_with_vectors(self, documents: list) -> list:
        self.fit(documents)
        self.doc_vectors = self.transform(documents)
        return self.doc_vectors


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.vocab = {}
        self.doc_len = []
        self.avgdl = 0
        self.doc_freqs = []
        self.idf = {}
        self.doc_tokens = []
        self._setup_iot_terms()
        self._setup_term_weights()

    def _setup_iot_terms(self):
        iot_terms = [
            'dp', 'DP', 'data_point', 'datapoint', 'data_point',
            'OTA', 'ota', 'dfu', 'DFU',
            'BLE', 'ble', 'bluetooth',
            'RS485', 'rs485', 'uart', 'UART', 'can', 'CAN',
            'MQTT', 'mqtt', 'HTTP', 'http',
            'HID', 'hid', 'hid_report',
            'BMS', 'bms', '电池管理',
            'DPID', 'dpid', 'fault', 'FAULT', 'alarm', 'ALARM',
            'rollover', 'Rollover', '碰撞', '震动', 'vibration',
            'OTA_START', 'ota_start', 'OTAUpgrade', 'ota_upgrade',
            'APP_SYNC_TIME', 'app_sync_time', 'time_sync',
            'DP_QUERY', 'dp_query', 'record_reported', '骑行记录',
            'vl_ble', 'vl_can', 'vl_iot', 'vl_app',
        ]
        for term in iot_terms:
            if term not in jieba.dt.FREQ:
                jieba.add_word(term, freq=100)

    def _setup_term_weights(self):
        self.term_weights = {}
        hex_pattern = re.compile(r'^0x[0-9a-fA-F]+$')
        dp_patterns = ['dp', 'dpid', 'dp_id', 'data_point', 'datapoint']
        cmd_patterns = ['cmd', 'command', 'frame_id', 'frameid', 'message_id', 'messageid']
        for term in hex_pattern.findall('0x0001 0x0003 0x8005 0x8003'):
            self.term_weights[term] = 2.5
        for pattern in dp_patterns:
            self.term_weights[pattern] = 2.0
        for pattern in cmd_patterns:
            self.term_weights[pattern] = 1.8
        self.term_weights['ota'] = 1.5
        self.term_weights['ble'] = 1.5
        self.term_weights['fault'] = 1.5
        self.term_weights['alarm'] = 1.5

    def _tokenize(self, text: str) -> list:
        text = text.lower()

        hex_codes = re.findall(r'0x[0-9a-fA-F]{1,8}', text)
        for hc in hex_codes:
            clean_hex = hc[2:] if hc.startswith('0x') else hc
            text = text.replace(hc, f' HEXCODE_{clean_hex} ')

        english_raw = re.findall(r'[a-z0-9_]+', text)
        english_words = []
        for word in english_raw:
            if word.startswith('hexcode_'):
                english_words.append(f'0x{word[9:]}')
            else:
                parts = word.split('_')
                english_words.extend([p for p in parts if len(p) >= 2])

        chinese_text = re.sub(r'[a-z0-9_\s]', '', text)
        chinese_words = list(jieba.cut(chinese_text))
        chinese_bigrams = []
        for i in range(len(chinese_words) - 1):
            combined = chinese_words[i] + chinese_words[i+1]
            if len(combined) >= 2:
                chinese_bigrams.append(combined)

        tokens = english_words + chinese_bigrams + [w for w in chinese_words if len(w) >= 2]

        dp_variants = ['dp', 'd p', 'd_p', 'data', 'data_point', 'datapoint']
        has_dp = any(t in dp_variants for t in tokens)
        if has_dp:
            tokens.extend(['dp', 'DP', 'data', 'Data'])

        return tokens[:5000]

    def fit(self, documents: list) -> None:
        if not documents:
            return

        self.doc_tokens = [self._tokenize(doc) for doc in documents]
        self.doc_len = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = sum(self.doc_len) / len(documents) if documents else 0

        df = Counter()
        for tokens in self.doc_tokens:
            unique = set(tokens)
            for t in unique:
                df[t] += 1

        self.vocab = {t: i for i, t in enumerate(df.keys())}
        self.idf = {}
        for t, freq in df.items():
            self.idf[t] = math.log((len(documents) - freq + 0.5) / (freq + 0.5) + 1)

    def score(self, query: str, doc_idx: int) -> float:
        if doc_idx >= len(self.doc_tokens) or not self.doc_tokens[doc_idx]:
            return 0.0

        query_tokens = self._tokenize(query)
        doc_tf = Counter(self.doc_tokens[doc_idx])
        doc_len = self.doc_len[doc_idx]

        score = 0.0
        for t in query_tokens:
            if t in self.vocab:
                tf = doc_tf.get(t, 0)
                idf = self.idf.get(t, 0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl)
                term_score = idf * numerator / denominator if denominator > 0 else 0
                weight = self.term_weights.get(t, 1.0)
                score += term_score * weight
        return score

    def search(self, query: str, top_k: int = 5) -> List[tuple]:
        if not self.doc_tokens:
            return []

        scores = [self.score(query, i) for i in range(len(self.doc_tokens))]
        indexed = [(i, s) for i, s in enumerate(scores) if s > 0]
        indexed.sort(key=lambda x: x[1], reverse=True)
        return indexed[:top_k]


def rrf_fusion(results_by_method: Dict[str, List[tuple]], k: int = 60) -> List[tuple]:
    """RRF (Reciprocal Rank Fusion) for combining multiple retrieval results."""
    doc_scores = {}
    for method_name, results in results_by_method.items():
        for rank, (doc_id, score) in enumerate(results):
            if doc_id not in doc_scores:
                doc_scores[doc_id] = 0.0
            doc_scores[doc_id] += 1.0 / (k + rank + 1)

    sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_docs


class LazyVectorStore:
    def __init__(self, metadata_db: MetadataDB, persist_dir: str = "knowledge_base/vectorized"):
        self.db = metadata_db
        self.persist_dir = persist_dir
        os.makedirs(persist_dir, exist_ok=True)
        self._global_tfidf = None
        self._loaded_files: Set[str] = set()
        self._file_vectors: Dict[str, list] = {}
        self._bm25_cache: Dict[str, tuple] = {}
        self._minimax_store = None
        self._use_minimax_embedding = True
        self._silicon_store = None
        self._use_silicon_embedding = False

    def _get_silicon_store(self):
        if self._silicon_store is None:
            try:
                from models.provider import create_embedding
                from config import EMBEDDING_PROVIDER
                if EMBEDDING_PROVIDER == "siliconflow":
                    self._silicon_store = create_embedding()
                    self._use_silicon_embedding = True
                    print(f"[LazyVectorStore] SiliconFlow embedding enabled")
                else:
                    self._silicon_store = None
                    self._use_silicon_embedding = False
            except ImportError:
                print("[LazyVectorStore] SiliconFlow embedding not available")
                self._silicon_store = None
                self._use_silicon_embedding = False
        return self._silicon_store

    def _get_global_tfidf(self):
        if self._global_tfidf is None:
            self._global_tfidf = SimpleTfidf(max_features=2000)
        return self._global_tfidf

    def _compute_content_hash(self, contents: List[str]) -> str:
        import hashlib
        content_str = '|'.join(contents)
        return hashlib.md5(content_str.encode()).hexdigest()

    def _vectorize_file(self, file_path: str, items: List[KnowledgeItem]) -> bool:
        if not items:
            return True

        try:
            contents = [item.content for item in items]
            content_hash = self._compute_content_hash(contents)

            cached = self.db.get_file_vectors(file_path)
            if cached:
                data = json.loads(cached)
                if data.get('hash') == content_hash:
                    self._file_vectors[file_path] = data['vectors']
                    self._loaded_files.add(file_path)
                    return True

            tfidf = SimpleTfidf(max_features=2000)
            vectors = tfidf.fit_transform(contents)

            vector_data = json.dumps({
                'hash': content_hash,
                'vectors': vectors,
                'ids': [item.id for item in items]
            })
            self.db.save_file_vectors(file_path, content_hash, vector_data, len(items))

            self._file_vectors[file_path] = vectors
            self._loaded_files.add(file_path)
            return True

        except Exception as e:
            print(f"Error vectorizing file {file_path}: {e}")
            return False

    def ensure_file_vectorized(self, file_path: str) -> bool:
        if file_path in self._loaded_files:
            return True

        items = self.db.get_items_by_file(file_path)
        if not items:
            return False

        return self._vectorize_file(file_path, items)

    def _build_faiss_index(self, vectors: List[List[float]], ids: List[str]) -> tuple:
        if not vectors:
            return None, {}

        dim = len(vectors[0])
        mat = np.array(vectors, dtype=np.float32)
        if dim == 0:
            return None, {}

        index = faiss.IndexFlatIP(dim)
        faiss.normalize_L2(mat)
        index.add(mat)

        id_map = {i: vid for i, vid in enumerate(ids)}
        return index, id_map

    def _faiss_search_in_file(self, file_path: str, query_vec: np.ndarray, top_k: int) -> List[Tuple[int, float]]:
        if file_path not in self._loaded_files or not self._file_vectors.get(file_path):
            return []

        vectors = self._file_vectors[file_path]
        if not vectors:
            return []

        ids = self.db.get_file_vectors(file_path)
        if ids:
            data = json.loads(ids)
            id_list = data.get('ids', [])
        else:
            return []

        dim = len(vectors[0])
        query_vec = query_vec.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(query_vec)

        index = faiss.IndexFlatIP(dim)
        mat = np.array(vectors, dtype=np.float32)
        faiss.normalize_L2(mat)
        index.add(mat)

        D, I = index.search(query_vec, min(top_k, len(vectors)))

        results = []
        for i, idx in enumerate(I[0]):
            if idx >= 0 and idx < len(id_list):
                results.append((idx, float(D[0][i])))
        return results

    def find_relevant_files(self, query: str, category: str = None, max_files: int = 10) -> tuple:
        import time
        t0 = time.time()
        TIMEOUT_SEC = 30

        query_lower = query.lower()
        query_tokens = set(re.findall(r'[a-z0-9_]+', query_lower))
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', query_lower)
        chinese_bigrams = set()
        for i in range(len(chinese_chars) - 1):
            chinese_bigrams.add(chinese_chars[i] + chinese_chars[i+1])

        expanded_keywords = set(query_tokens)
        for bigram in chinese_bigrams:
            expanded_keywords.add(bigram)
            if bigram in CHINESE_TO_ENGLISH_MAP:
                expanded_keywords.update(CHINESE_TO_ENGLISH_MAP[bigram])

        query_keywords = expanded_keywords

        # 优先使用FTS5进行全文搜索
        fts_files = self.db.search_fts(query)
        if fts_files:
            if category:
                category_files = set(self.db.get_files_by_category(category))
                fts_files = [f for f in fts_files if f in category_files]
            # Pre-populate items cache and file_scores for FTS5 results
            file_items_cache = {}
            file_scores = []
            business_docs = []
            other_docs = []

            # Separate business docs from other files
            for fp in fts_files:
                if 'protocol_docs' in fp or 'business_docs' in fp:
                    business_docs.append(fp)
                else:
                    other_docs.append(fp)

            # Process business docs first (up to max_files * 3)
            for fp in business_docs[:max_files * 3]:
                items = self.db.get_items_by_file(fp)
                if items:
                    file_items_cache[fp] = items
                    file_scores.append((fp, 1001.0, len(items)))

            # Then fill in with other docs (up to max_files)
            for fp in other_docs[:max_files]:
                items = self.db.get_items_by_file(fp)
                if items:
                    file_items_cache[fp] = items
                    file_scores.append((fp, 1.0, len(items)))

            file_scores.sort(key=lambda x: (x[1], -x[2]), reverse=True)
            return [f[0] for f in file_scores[:max_files]], file_items_cache

        if category == 'protocol':
            all_files = self.db.get_files_by_category('protocol')
        elif category == 'c_code':
            all_files = self.db.get_files_by_category('c_code')
        elif category == 'log':
            all_files = self.db.get_files_by_category('log')
        else:
            all_files = self.db.get_all_files()

        file_scores = []
        file_items_cache = {}

        for file_path in all_files:
            if time.time() - t0 > TIMEOUT_SEC:
                break
            items = self.db.get_items_by_file(file_path)
            if not items:
                continue
            file_items_cache[file_path] = items
            if category and items[0].category != category:
                continue

            filename = os.path.basename(file_path).lower()
            raw_file_tokens = re.findall(r'[a-z0-9_]+', filename)
            file_tokens = set()
            for token in raw_file_tokens:
                file_tokens.add(token)
                file_tokens.update(token.split('_'))
            filename_chinese = re.findall(r'[\u4e00-\u9fff]', filename)
            filename_bigrams = set()
            for i in range(len(filename_chinese) - 1):
                filename_bigrams.add(filename_chinese[i] + filename_chinese[i+1])
            file_keywords = file_tokens | filename_bigrams

            score = len(query_keywords & file_keywords)

            id_content = ' '.join([item.id.lower() for item in items])
            raw_tokens = re.findall(r'[a-z0-9_]+', id_content)
            id_tokens = set()
            for token in raw_tokens:
                id_tokens.add(token)
                id_tokens.update(token.split('_'))
            id_content_chars = re.findall(r'[一-鿿]', id_content)
            id_bigrams = set()
            for i in range(len(id_content_chars) - 1):
                id_bigrams.add(id_content_chars[i] + id_content_chars[i+1])
            id_keywords = id_tokens | id_bigrams
            id_score = len(query_keywords & id_keywords)
            score = max(score, id_score)

            # Require at least one Chinese char from query to be present in filename or id_content
            # This avoids false positives like 'log' matching 'keylog_export'
            if chinese_chars:
                filename_lower = filename.lower()
                id_content_lower = id_content.lower()
                has_chinese_match = any(
                    char in filename_lower or char in id_content_lower
                    for char in chinese_chars
                )
                if not has_chinese_match:
                    score = 0

            if score > 0:
                file_scores.append((file_path, score, len(items)))

        def sort_key(x):
            score = x[1]
            path = x[0]
            item_count = x[2] if len(x) > 2 else 0
            is_business_doc = 1 if ('business_docs' in path or 'manual/protocol_docs' in path) else 0
            effective_score = score + (1000 if is_business_doc and score > 0 else 0)
            return (effective_score, is_business_doc, -item_count)

        file_scores.sort(key=sort_key, reverse=True)
        return [f[0] for f in file_scores[:max_files]], file_items_cache

    def _get_or_create_bm25(self, file_path: str, items: List[KnowledgeItem]) -> tuple:
        cache_key = f"{file_path}_{len(items)}"
        if cache_key in self._bm25_cache:
            return self._bm25_cache[cache_key]

        contents = [item.content for item in items]
        bm25 = BM25()
        bm25.fit(contents)
        result = (bm25, items)
        self._bm25_cache[cache_key] = result
        return result

    def _get_or_create_tfidf(self, file_path: str, items: List[KnowledgeItem]) -> tuple:
        cache_key = f"tfidf_{file_path}_{len(items)}"
        if cache_key in self._bm25_cache:
            return self._bm25_cache[cache_key]

        contents = [item.content for item in items]
        tfidf = SimpleTfidf(max_features=2000)
        tfidf.fit_with_vectors(contents)
        result = (tfidf, items)
        self._bm25_cache[cache_key] = result
        return result

    def search(self, query: str, category: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        import time
        t0 = time.time()
        TIMEOUT_SEC = 30

        BUSINESS_DOC_WEIGHT = 10.0
        BUSINESS_DOC_TYPES = {'business_doc', 'protocol_doc'}

        expander = QueryExpander()
        expanded_queries = expander.expand(query)[:1]
        structured_query = expander.build_structured_query(query)

        # Use ordered dict to preserve FTS5 priority (business docs first)
        import collections
        relevant_files_ordered = collections.OrderedDict()
        shared_items_cache = {}
        for eq in expanded_queries:
            if time.time() - t0 > TIMEOUT_SEC:
                break
            files, items_cache = self.find_relevant_files(eq, category, max_files=20)
            # Preserve order: first occurrence of each file is kept
            for f in files:
                if f not in relevant_files_ordered:
                    relevant_files_ordered[f] = True
            for f, items in items_cache.items():
                if f not in shared_items_cache:
                    shared_items_cache[f] = items
        relevant_files = list(relevant_files_ordered.keys())[:20]
        item_map = []
        file_item_ranges = []
        doc_id_to_info = {}

        bm25_combined = {}
        tfidf_combined = {}
        faiss_combined = {}

        use_silicon = self._get_silicon_store() is not None

        for file_path in relevant_files:
            items = shared_items_cache.get(file_path)
            if not items:
                continue

            filtered_items = [item for item in items if not category or item.category == category]
            if not filtered_items:
                continue

            start_idx = len(item_map)
            vectors = self._file_vectors.get(file_path, [])
            item_ids = [item.id for item in items]

            for item in filtered_items:
                item_map.append({
                    'id': item.id,
                    'source': file_path,
                    'title': item.title,
                    'content': item.content[:500],
                    'type': item.type,
                    'metadata': item.metadata,
                    'scene': getattr(item, 'scene', '') or ''
                })
                doc_id_to_info[item.id] = len(item_map) - 1
            file_item_ranges.append((file_path, start_idx, len(item_map)))

            bm25, _ = self._get_or_create_bm25(file_path, filtered_items)
            tfidf, _ = self._get_or_create_tfidf(file_path, filtered_items)

            query_vec = None
            for eq in expanded_queries:
                if query_vec is None:
                    query_vec = tfidf.query(eq)
                    query_vec_np = np.array([query_vec], dtype=np.float32)
                    if query_vec_np.shape[1] > 0:
                        faiss.normalize_L2(query_vec_np)

                bm25_scores = bm25.search(eq, top_k=max(50, top_k * 3))
                for doc_idx, score in bm25_scores:
                    actual_idx = start_idx + doc_idx
                    if actual_idx >= len(item_map):
                        continue
                    doc_id = item_map[actual_idx]['id']
                    bm25_combined[doc_id] = bm25_combined.get(doc_id, 0.0) + score

                tfidf_scores = tfidf.search(eq, top_k=max(50, top_k * 3))
                for doc_idx, score in tfidf_scores:
                    actual_idx = start_idx + doc_idx
                    if actual_idx >= len(item_map):
                        continue
                    doc_id = item_map[actual_idx]['id']
                    tfidf_combined[doc_id] = tfidf_combined.get(doc_id, 0.0) + score

            if use_silicon and len(vectors) > 0:
                try:
                    contents = [item.content for item in filtered_items]
                    silicon_embeddings = self._silicon_store.encode(contents)
                    if len(silicon_embeddings) == len(vectors):
                        mat = np.array(silicon_embeddings, dtype=np.float32)
                        faiss.normalize_L2(mat)
                        dim = mat.shape[1]

                        query_emb = self._silicon_store.encode([expander.expand(query)[0]])
                        query_emb_np = np.array(query_emb, dtype=np.float32)
                        faiss.normalize_L2(query_emb_np)

                        index = faiss.IndexFlatIP(dim)
                        index.add(mat)
                        D, I = index.search(query_emb_np, min(50, len(vectors)))
                        for i, idx in enumerate(I[0]):
                            if idx >= 0 and idx < len(item_ids):
                                doc_id = item_ids[idx]
                                if doc_id in doc_id_to_info:
                                    faiss_combined[doc_id] = max(faiss_combined.get(doc_id, 0.0), float(D[0][i]))
                except Exception as e:
                    print(f"[LazyVectorStore] SiliconFlow search error: {e}")
            elif query_vec is not None and len(vectors) > 0 and query_vec_np.shape[1] > 0:
                try:
                    mat = np.array(vectors, dtype=np.float32)
                    faiss.normalize_L2(mat)

                    dim = mat.shape[1]
                    # HNSW暂不可用：faiss-cpu 1.8.0 Windows版IndexHNSWFlat.add()存在segfault
                    # TODO: 待环境修复后切换为HNSW以提升大数据集性能
                    # if len(vectors) > 100:
                    #     index = faiss.IndexHNSWFlat(dim, 32)
                    #     index.hnsw.efSearch = 64
                    #     index.hnsw.efConstruction = 40
                    # else:
                    index = faiss.IndexFlatIP(dim)
                    index.add(mat)
                    D, I = index.search(query_vec_np, min(50, len(vectors)))
                    for i, idx in enumerate(I[0]):
                        if idx >= 0 and idx < len(item_ids):
                            doc_id = item_ids[idx]
                            if doc_id in doc_id_to_info:
                                faiss_combined[doc_id] = max(faiss_combined.get(doc_id, 0.0), float(D[0][i]))
                except Exception as e:
                    pass

        if not bm25_combined:
            # Fallback: if category filter resulted in 0 results, retry without category
            if category is not None:
                return self.search(query, category=None, top_k=top_k)
            return []

        bm25_ranked = sorted(bm25_combined.items(), key=lambda x: x[1], reverse=True)
        tfidf_ranked = sorted(tfidf_combined.items(), key=lambda x: x[1], reverse=True)
        faiss_ranked = sorted(faiss_combined.items(), key=lambda x: x[1], reverse=True)

        rrf_results = rrf_fusion({
            'bm25': bm25_ranked[:50],
            'tfidf': tfidf_ranked[:50],
            'faiss': faiss_ranked[:50]
        }, k=60)

        final_results = []
        query_lower = query.lower()

        SCENE_PATTERNS = ['场景', '条件', '触发', '何时', '什么情况', '使用情况', '适用']
        has_scene_query = any(p in query_lower for p in SCENE_PATTERNS)

        for doc_id, rrf_score in rrf_results[:top_k]:
            if doc_id in doc_id_to_info:
                item_idx = doc_id_to_info[doc_id]
                item_info = item_map[item_idx]
                doc_type = item_info.get('type', '')
                if doc_type in BUSINESS_DOC_TYPES:
                    rrf_score *= BUSINESS_DOC_WEIGHT

                title = item_info.get('title', '')
                title_lower = title.lower()
                if query_lower in title_lower:
                    rrf_score *= 2.0

                scene = item_info.get('scene', '')
                if scene:
                    scene_lower = scene.lower()
                    if query_lower in scene_lower:
                        rrf_score *= 1.5
                    if has_scene_query:
                        for p in SCENE_PATTERNS:
                            if p in scene_lower:
                                rrf_score *= 1.2
                                break

                # 子系统上下文验证：GPS/定位相关查询不应匹配到BLE/其他子系统
                metadata = item_info.get('metadata', {})
                item_subsystem = metadata.get('subsystem', '')
                item_context = metadata.get('context', '')

                # 整车电源/开机相关查询，应该优先匹配 can/vehicle 子系统
                if item_subsystem:
                    query_lower = query.lower()
                    # GPS/定位相关关键词
                    gps_keywords = ['搜星', '定位', 'GPS', 'gil', '卫星', '位置', 'run_state']
                    # 整车控制器相关关键词
                    vehicle_keywords = ['控制器', '整车', 'CAN', 'FE01', '开机', '电源', 'VCU']

                    is_gps_query = any(k in query_lower for k in gps_keywords)
                    is_vehicle_query = any(k in query_lower for k in vehicle_keywords)

                    # 如果是GPS相关查询，降低非GPS子系统的得分
                    if is_gps_query and 'gps' not in item_subsystem.lower() and 'gil' not in item_subsystem.lower():
                        if 'can' in item_subsystem.lower() or 'vehicle' in item_subsystem.lower():
                            rrf_score *= 0.3

                    # 如果是整车控制器查询，降低GPS子系统的得分
                    if is_vehicle_query and ('gps' in item_subsystem.lower() or 'gil' in item_subsystem.lower()):
                        rrf_score *= 0.3

                final_results.append({
                    'id': doc_id,
                    'score': float(rrf_score),
                    'source': item_info['source'],
                    'title': item_info['title'],
                    'content_preview': item_info['content'][:800]
                })

        # Deduplicate by source file - keep highest scoring result per file
        seen_sources = {}
        for r in final_results:
            src = r['source']
            if src not in seen_sources or r['score'] > seen_sources[src]['score']:
                seen_sources[src] = r

        # Re-sort by score
        final_results = sorted(seen_sources.values(), key=lambda x: x['score'], reverse=True)

        if len(final_results) > 3:
            try:
                from models.provider import create_reranker
                from config import RERANK_PROVIDER
                reranker = create_reranker(RERANK_PROVIDER)
                final_results = reranker.rerank(query, final_results[:10], top_k=top_k)
            except Exception as e:
                pass

        latency = time.time() - t0
        print(f"[SEARCH] query=\"{query}\" category={category} top_k={top_k} latency={latency:.3f}s results={len(final_results)}")

        return final_results

    def _rerank_with_crossencoder(self, query: str, candidates: List[Dict]) -> List[Dict]:
        try:
            from sentence_transformers import CrossEncoder
            model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

            doc_pairs = [(query, r['content_preview']) for r in candidates]
            scores = model.predict(doc_pairs)

            for i, r in enumerate(candidates):
                r['cross_score'] = float(scores[i])

            reranked = sorted(candidates, key=lambda x: x.get('cross_score', 0), reverse=True)
            for r in reranked:
                r['score'] = r.get('cross_score', r['score'])

            return reranked
        except Exception as e:
            return candidates

    def search_with_minimax_hybrid(
        self,
        query: str,
        category: str = None,
        top_k: int = 5,
        alpha: float = 0.5,
        use_minimax: bool = True
    ) -> List[Dict[str, Any]]:
        """
        混合检索：BM25 + TF-IDF + MiniMax稠密检索 + RRF融合

        Args:
            query: 查询文本
            category: 文档分类过滤
            top_k: 返回结果数量
            alpha: 稠密检索权重 (0.5表示BM25和MiniMax平等对待)
            use_minimax: 是否启用MiniMax稠密检索

        Returns:
            融合后的检索结果
        """
        from models.minimax_embedding import rrf_fusion

        t0 = time.time()

        expander = QueryExpander()
        expanded_queries = expander.expand(query)[:1]

        relevant_files = set()
        shared_items_cache = {}
        for eq in expanded_queries:
            files, items_cache = self.find_relevant_files(eq, category, max_files=20)
            relevant_files.update(files)
            for f, items in items_cache.items():
                if f not in shared_items_cache:
                    shared_items_cache[f] = items
        relevant_files = list(relevant_files)[:20]

        item_map = []
        doc_id_to_info = {}

        bm25_combined = {}
        tfidf_combined = {}

        for file_path in relevant_files:
            items = shared_items_cache.get(file_path)
            if not items:
                continue

            filtered_items = [item for item in items if not category or item.category == category]
            if not filtered_items:
                continue

            for item in filtered_items:
                item_map.append({
                    'id': item.id,
                    'source': file_path,
                    'title': item.title,
                    'content': item.content[:500],
                    'type': item.type,
                    'metadata': item.metadata
                })
                doc_id_to_info[item.id] = len(item_map) - 1

            bm25, _ = self._get_or_create_bm25(file_path, filtered_items)
            tfidf, _ = self._get_or_create_tfidf(file_path, filtered_items)

            for eq in expanded_queries:
                bm25_scores = bm25.search(eq, top_k=max(50, top_k * 3))
                for doc_idx, score in bm25_scores:
                    if doc_idx < len(item_map):
                        doc_id = item_map[doc_idx]['id']
                        bm25_combined[doc_id] = bm25_combined.get(doc_id, 0.0) + score

                tfidf_vec = tfidf.query(eq)
                tfidf_scores = tfidf.search(eq, top_k=max(50, top_k * 3))
                for doc_idx, score in tfidf_scores:
                    if doc_idx < len(item_map):
                        doc_id = item_map[doc_idx]['id']
                        tfidf_combined[doc_id] = tfidf_combined.get(doc_id, 0.0) + score

        bm25_ranked = sorted(bm25_combined.items(), key=lambda x: x[1], reverse=True)[:50]
        tfidf_ranked = sorted(tfidf_combined.items(), key=lambda x: x[1], reverse=True)[:50]

        if use_minimax and self._use_minimax_embedding:
            minimax_store = self._get_minimax_store()
            if minimax_store:
                all_texts = [item['content'] for item in item_map]
                all_ids = [item['id'] for item in item_map]
                minimax_store.add_docs_batch([{'id': id, 'text': text} for id, text in zip(all_ids, all_texts)])
                dense_results = minimax_store.search(query, top_k=top_k * 3)
                dense_ranked = [(doc_id, score) for doc_id, score in dense_results]

                results_list = [bm25_ranked, dense_ranked]
            else:
                results_list = [bm25_ranked, tfidf_ranked]
        else:
            results_list = [bm25_ranked, tfidf_ranked]

        rrf_results = rrf_fusion(results_list, k=60)

        final_results = []
        for doc_id, rrf_score in rrf_results[:top_k]:
            if doc_id in doc_id_to_info:
                idx = doc_id_to_info[doc_id]
                item = item_map[idx]
                item['score'] = rrf_score
                final_results.append(item)

        latency = time.time() - t0
        print(f"[HYBRID_SEARCH] query=\"{query}\" category={category} top_k={top_k} latency={latency:.3f}s results={len(final_results)}")

        return final_results


class KnowledgeBase:
    def __init__(self, db_path: str = "data/metadata.db", vector_dir: str = "knowledge_base/vectorized"):
        self.metadata_db = MetadataDB(db_path)
        self.vector_store = LazyVectorStore(self.metadata_db, vector_dir)
        self.intent_classifier = QueryIntentClassifier()

    def add_c_code(self, blocks: List[Dict[str, Any]]) -> int:
        items = [
            KnowledgeItem(
                id=block['id'],
                type=block['type'],
                category='c_code',
                title=f"{block['name']} ({block['type']})",
                content=block['content'],
                source_file=block['file_path'],
                line_number=block['line_number'],
                created_at=datetime.now().isoformat(),
                metadata={'description': block.get('description', '')}
            )
            for block in blocks
        ]
        return self.metadata_db.insert_items_batch(items)

    def add_protocol_docs(self, docs: List[Dict[str, Any]]) -> int:
        def to_dict(doc, i):
            if hasattr(doc, 'get'):
                return doc
            return {
                'id': getattr(doc, 'id', f"doc_{i}"),
                'type': getattr(doc, 'type', 'protocol_doc'),
                'title': getattr(doc, 'name', 'Untitled'),
                'content': getattr(doc, 'content', ''),
                'source': getattr(doc, 'source', ''),
                'scene': getattr(doc, 'scene', '')
            }

        items = [
            KnowledgeItem(
                id=to_dict(doc, i).get('id', f"doc_{i}"),
                type=to_dict(doc, i).get('type', 'protocol_doc'),
                category='protocol',
                title=to_dict(doc, i).get('title', 'Untitled'),
                content=to_dict(doc, i).get('content', ''),
                source_file=to_dict(doc, i).get('source', 'knowledge_base/manual/protocol_docs'),
                line_number=0,
                created_at=datetime.now().isoformat(),
                metadata={'scene': to_dict(doc, i).get('scene', '')}
            )
            for i, doc in enumerate(docs)
        ]
        return self.metadata_db.insert_items_batch(items)

    def add_logs(self, logs: List[Dict[str, Any]]) -> int:
        items = [
            KnowledgeItem(
                id=log['id'],
                type='log_entry',
                category='log',
                title=f"Log line {log['line_number']}",
                content=log.get('message', log.get('raw_line', '')),
                source_file=log.get('source_file', 'log'),
                line_number=log['line_number'],
                created_at=datetime.now().isoformat(),
                metadata={'level': log.get('level', ''), 'timestamp': log.get('timestamp', '')}
            )
            for log in logs
        ]
        return self.metadata_db.insert_items_batch(items)

    def search(self, query: str, category: str = None, top_k: int = 5) -> List[KnowledgeItem]:
        if category is None:
            category = self.intent_classifier.classify(query)

        results = self.vector_store.search(query, category, top_k)

        if not results:
            return []

        item_ids = [r['id'] for r in results]
        items = self.metadata_db.search_items(item_ids)

        id_to_item = {item.id: item for item in items}
        ordered_items = [id_to_item.get(id) for id in item_ids if id in id_to_item]
        return [item for item in ordered_items if item is not None][:top_k]

    def add_feedback(self, question: str, answer: str, is_resolved: bool = False):
        return self.metadata_db.add_feedback(question, answer, is_resolved)

    def get_unresolved_questions(self) -> List[Dict[str, Any]]:
        return self.metadata_db.get_unresolved_feedback()

    def update_knowledge_item(self, item_id: str, content: str = None, title: str = None,
                               metadata: Dict[str, Any] = None) -> bool:
        success = self.metadata_db.update_item(item_id, content, title, metadata)
        if success:
            item = self.metadata_db.search_items([item_id])
            if item:
                self.vector_store.ensure_file_vectorized(item[0].source_file)
        return success

    def delete_knowledge_item(self, item_id: str) -> bool:
        return self.metadata_db.delete_item(item_id)

    def find_related_items(self, question: str, limit: int = 5) -> List[KnowledgeItem]:
        return self.metadata_db.search_items_by_content(question, limit)

    def search_with_parent(self, query: str, category: str = None, top_k: int = 5) -> List[KnowledgeItem]:
        results = self.vector_store.search(query, category, top_k)

        if not results:
            return []

        item_ids = [r['id'] for r in results]
        items = self.metadata_db.search_items(item_ids)

        id_to_item = {item.id: item for item in items}
        ordered_items = [id_to_item.get(id) for id in item_ids if id in id_to_item]

        final_items = []
        for item in ordered_items:
            if item is None:
                continue
            if item.parent_id:
                parent = self.metadata_db.get_parent_document(item.parent_id)
                if parent:
                    final_items.append(parent)
                else:
                    final_items.append(item)
            else:
                final_items.append(item)

        return final_items[:top_k]

    def add_graph_nodes(self, nodes: List[Dict], edges: List[Dict], batch_size: int = 500) -> int:
        """添加图节点和边到知识库（分批处理）"""
        total_added = 0
        for i in range(0, len(nodes), batch_size):
            batch = nodes[i:i + batch_size]
            items = []
            for node in batch:
                node_id = node.get('id', f"node_{hash(node.get('name', ''))}")
                item = KnowledgeItem(
                    id=node_id,
                    type=f"graph_{node.get('type', 'node')}",
                    category='graph',
                    title=node.get('name', node_id),
                    content=node.get('code_snippet', ''),
                    source_file=node.get('file', ''),
                    line_number=node.get('line_start', 0),
                    created_at=datetime.now().isoformat(),
                    metadata={
                        'node_type': node.get('type', 'unknown'),
                        'subsystem': node.get('subsystem', ''),
                        'context': node.get('context', ''),
                        'edges': self._get_edges_for_node(node_id, edges),
                        'keywords': self._extract_keywords(node)
                    }
                )
                items.append(item)

            if items:
                self.metadata_db.insert_items_batch(items)
                total_added += len(items)
                print(f"[GraphIndex] Batch {i//batch_size + 1}: added {len(items)} nodes")

        return total_added

    def _get_edges_for_node(self, node_id: str, edges: List[Dict]) -> List[Dict]:
        node_edges = []
        for edge in edges:
            if edge.get('from_node') == node_id or edge.get('to_node') == node_id:
                node_edges.append({
                    'type': edge.get('edge_type', 'related'),
                    'target': edge.get('to_node') if edge.get('from_node') == node_id else edge.get('from_node'),
                    'direction': 'out' if edge.get('from_node') == node_id else 'in'
                })
        return node_edges

    def _extract_keywords(self, node: Dict) -> str:
        keywords = []
        if node.get('type') == 'function':
            keywords.append('function')
            if node.get('metadata', {}).get('params'):
                keywords.append('has_params')
        if node.get('type') == 'variable':
            keywords.append('variable')
        keywords.append(node.get('name', ''))
        return ','.join(keywords)

    def search_graph(self, query: str, top_k: int = 5) -> List[KnowledgeItem]:
        """搜索图节点"""
        return self.metadata_db.search_items_by_content(query, limit=top_k, category='graph')

    def get_callers(self, func_name: str) -> List[KnowledgeItem]:
        """获取调用指定函数的所有函数节点"""
        return self.metadata_db.search_items_by_content(func_name, limit=50, category='graph')

    def get_callees(self, func_name: str) -> List[KnowledgeItem]:
        """获取指定函数调用的所有函数节点"""
        return self.metadata_db.search_items_by_content(func_name, limit=50, category='graph')


class QueryIntentClassifier:
    CATEGORY_PATTERNS = {
        'protocol': [
            'BLE', '蓝牙', '配对', '绑定', 'pair', 'bond', 'advertis', 'scan',
            'HID', 'OTA', 'DFU', 'RS485', 'CAN', 'MQTT', '协议', '命令', '上报',
            'DP', '数据点', '物模型', 'datapoint', 'frame', '帧', 'CRC', '校验',
            '骑行', '行程', '轨迹', '记录', 'log'
        ],
        'log': [
            'log', '日志', 'error', '错误', 'fault', '故障', 'warn', '警告',
            'exception', '异常', 'crash', '崩溃', 'dump', 'trace', '调试'
        ],
        'c_code': [
            'struct', 'function', 'enum', 'macro', 'typedef', 'define', '变量',
            '函数', '头文件', 'include', 'source', 'impl', 'implementation'
        ]
    }

    def classify(self, query: str) -> str:
        query_lower = query.lower()
        scores = {}

        for category, patterns in self.CATEGORY_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if pattern.lower() in query_lower:
                    score += 1
            scores[category] = score

        max_score = max(scores.values()) if scores else 0
        if max_score == 0:
            return None

        for category, score in scores.items():
            if score == max_score:
                return category

        return None

    def get_search_terms(self, query: str, category: str = None) -> List[str]:
        terms = [query]
        query_lower = query.lower()

        if category == 'protocol':
            protocol_terms = ['BLE', 'protocol', '命令', '上报', 'DP', 'RS485', 'CAN']
            for term in protocol_terms:
                if term.lower() not in query_lower:
                    terms.append(f"{query} {term}")
        elif category == 'c_code':
            code_terms = ['struct', 'function', 'enum', 'function']
            for term in code_terms:
                if term.lower() not in query_lower:
                    terms.append(f"{query} {term}")

        return terms[:3]