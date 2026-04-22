import json
import re
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
import sys
sys.path.insert(0, r'D:\workspace\Agent')
from models.enhanced_rag_engine import CODE_TO_BUSINESS_MAP


LEAKAGE_INDICATORS = [
    r'0x[0-9A-Fa-f]{2,}',
    r'\b\w+_t\b',
    r'->\w+',
    r'\*\w+',
    r'\w+\s*\([^)]*\)',
    r'\[\s*\w+\s*\]',
    r'\b\d+\b',
]

IF_TEMPLATE = "当{condition}时，触发{action}"
SWITCH_TEMPLATE = "系统根据{variable}的不同取值，进入对应的业务处理分支"
WHILE_TEMPLATE = "当{condition}满足时，持续执行{action}"

NEGATIVE_FEW_SHOT = '''

【正反例对比】
❌ 违规描述：系统检查 crc16 == 0 来判断校验是否通过
✅ 合规描述：系统通过标准循环冗余校验确认数据包传输完整性

❌ 违规描述：如果 temp_buffer[i] > threshold 则触发 alarm
✅ 合规描述：当传感器读数超过预设阈值时，系统触发告警机制

❌ 违规描述：调用 send_data(ptr, len) 发送数据包
✅ 合规描述：系统通过预设通道向目标终端传输数据'''


@dataclass
class DistilledKnowledge:
    node_id: str
    node_type: str
    original_code: str
    distilled_content: str
    business_description: str
    keywords: List[str]
    metadata: Dict[str, Any]


class CodeDistiller:
    DISTILL_PROMPT_TEMPLATE = """你是一个专业的物联网嵌入式系统产品经理，负责将代码逻辑"蒸馏"为业务描述。

【核心原则】把自己当作一个**只看产品说明书、不看源码**的用户，用业务语言描述功能。

【输入代码】
```c
{code_snippet}
```

{NEGATIVE_FEW_SHOT}

【任务】
将上述代码转化为业务逻辑描述，遵循以下原则：

1. **提取功能意图**：这段代码"做什么"而非"怎么做"
2. **使用业务语言**：用"数据上报"、"状态同步"、"协议解析"等术语
3. **隐藏实现细节**：
   - 禁止出现具体变量名（如 retry_count, temp_buffer）
   - 禁止出现函数签名
   - 用泛化描述替代（如"重试计数器"、"临时缓存"）
4. **保持逻辑完整**：不丢失条件判断、分支逻辑

【输出格式】
```json
{{
    "functionality": "核心功能一句话描述",
    "business_logic": "详细业务逻辑描述（2-3句）",
    "key_conditions": ["关键条件1", "关键条件2"],
    "outputs": ["输出/副作用1", "输出/副作用2"],
    "business_terms": ["相关业务术语1", "相关业务术语2"]
}}
```

请直接输出JSON，不要有其他文字："""

    STATE_MACHINE_DISTILL_TEMPLATE = """你是一个专业的物联网协议分析师，负责将状态机代码转化为业务逻辑描述。

【输入状态机】
```c
{state_machine_code}
```

【任务】
将上述状态机转化为业务逻辑描述，遵循以下原则：

1. **识别状态含义**：每个状态对应什么业务状态（如"等待配对"、"连接中"、"已连接"）
2. **提炼转移条件**：状态转移的业务条件（如"收到配对请求"、"认证成功"、"超时"）
3. **描述动作**：转移时执行的业务动作（如"发送响应"、"启动计时器"）
4. **使用业务术语**：不用技术术语，用业务语言

【输出格式】
```json
{{
    "purpose": "状态机的业务目的",
    "states": [
        {{"name": "业务状态名", "description": "状态含义"}},
        ...
    ],
    "transitions": [
        {{"from": "源状态", "to": "目标状态", "trigger": "触发条件", "action": "业务动作"}},
        ...
    ],
    "initial_state": "初始状态",
    "business_flow": "整体业务流程简述"
}}
```

请直接输出JSON，不要有其他文字："""

    def __init__(self, api_key: str = None, base_url: str = "https://api.minimax.chat/v1"):
        self.api_key = api_key
        self.base_url = base_url
        self._api_key = None
        self._load_config()

    def _load_config(self):
        try:
            from config import MINIMAX_API_KEY, PROXIES
            self._api_key = MINIMAX_API_KEY
            self._proxies = PROXIES
        except ImportError:
            print("Warning: config.py not found, using default settings")

    def distill_function(self, code_snippet: str, function_name: str = "") -> Optional[Dict]:
        prompt = self.DISTILL_PROMPT_TEMPLATE.format(
            code_snippet=code_snippet[:500],
            NEGATIVE_FEW_SHOT=NEGATIVE_FEW_SHOT
        )

        try:
            result = self._call_llm(prompt)
            if result:
                parsed = json.loads(result)
                parsed['function_name'] = function_name
                return parsed
        except json.JSONDecodeError:
            print(f"Failed to parse LLM response as JSON for function {function_name}")
        except Exception as e:
            print(f"Error distilling function {function_name}: {e}")

        return self._fallback_distill(code_snippet, "function")

    def distill_state_machine(self, state_machine_code: str, sm_name: str = "") -> Optional[Dict]:
        prompt = self.STATE_MACHINE_DISTILL_TEMPLATE.format(state_machine_code=state_machine_code[:800])

        try:
            result = self._call_llm(prompt)
            if result:
                parsed = json.loads(result)
                parsed['sm_name'] = sm_name
                return parsed
        except json.JSONDecodeError:
            print(f"Failed to parse LLM response as JSON for state machine {sm_name}")
        except Exception as e:
            print(f"Error distilling state machine {sm_name}: {e}")

        return self._fallback_distill(state_machine_code, "state_machine")

    def _call_llm(self, prompt: str) -> Optional[str]:
        if not self._api_key:
            return None

        import requests

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "MiniMax-M2.7",
            "max_tokens": 600,
            "temperature": 0.3,
            "messages": [{"role": "user", "content": prompt}]
        }

        try:
            session = requests.Session()
            if hasattr(self, '_proxies'):
                session.proxies = self._proxies
            else:
                session.trust_env = False

            response = session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )

            if response.status_code() == 200:
                result = response.json()
                if result.get("choices"):
                    return result["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"LLM API call failed: {e}")

        return None

    def _fallback_distill(self, code: str, code_type: str) -> Dict:
        logic_desc = self._generate_logic_from_template(code, code_type)
        if code_type == "function":
            return {
                "functionality": self._extract_functionality_fallback(code),
                "business_logic": logic_desc,
                "key_conditions": self._extract_conditions_fallback(code),
                "outputs": self._extract_outputs_fallback(code),
                "business_terms": self._extract_business_terms(code)
            }
        elif code_type == "state_machine":
            return {
                "purpose": "状态机处理流程",
                "states": [{"name": s, "description": ""} for s in self._extract_states_fallback(code)],
                "transitions": [],
                "initial_state": "",
                "business_flow": logic_desc
            }
        else:
            return {
                "functionality": "代码逻辑块",
                "business_logic": logic_desc,
                "key_conditions": [],
                "outputs": [],
                "business_terms": []
            }

    def _extract_functionality_fallback(self, code: str) -> str:
        code_lower = code.lower()

        if 'init' in code_lower:
            return "初始化模块"
        elif 'send' in code_lower or 'transmit' in code_lower:
            return "数据发送处理"
        elif 'receive' in code_lower or 'recv' in code_lower:
            return "数据接收处理"
        elif 'check' in code_lower or 'verify' in code_lower:
            return "数据校验处理"
        elif 'parse' in code_lower or 'decode' in code_lower:
            return "协议解析处理"
        elif 'encode' in code_lower:
            return "协议编码处理"
        elif 'timeout' in code_lower or 'overtime' in code_lower:
            return "超时处理逻辑"
        elif 'retry' in code_lower:
            return "重试机制"
        elif 'error' in code_lower or 'fault' in code_lower:
            return "错误处理逻辑"
        elif 'state' in code_lower or 'status' in code_lower:
            return "状态管理"
        else:
            return "业务逻辑处理"

    def _extract_conditions_fallback(self, code: str) -> List[str]:
        conditions = []
        if 'if(' in code:
            conditions.append("条件分支")
        if 'switch' in code.lower():
            conditions.append("多分支选择")
        if 'while' in code.lower():
            conditions.append("循环条件")
        if 'for' in code.lower():
            conditions.append("迭代条件")
        return conditions

    def _extract_outputs_fallback(self, code: str) -> List[str]:
        outputs = []
        if 'return' in code:
            outputs.append("返回值")
        if 'send' in code.lower():
            outputs.append("发送数据")
        if 'set' in code.lower():
            outputs.append("状态设置")
        if 'update' in code.lower():
            outputs.append("数据更新")
        return outputs

    def _extract_business_terms(self, code: str) -> List[str]:
        terms = []
        code_lower = code.lower()

        term_mapping = {
            'ble': ['BLE', '蓝牙'],
            'bluetooth': ['BLE', '蓝牙'],
            'pair': ['配对', '绑定'],
            'bond': ['配对', '绑定'],
            'ota': ['OTA', '升级'],
            'update': ['OTA', '升级'],
            'dp': ['数据点', 'DP'],
            'datapoint': ['数据点', 'DP'],
            'report': ['上报', '报告'],
            'upload': ['上传', '上报'],
            'battery': ['电池', '电量'],
            'speed': ['速度', '车速'],
            'mileage': ['里程', '距离'],
            'fault': ['故障', '异常'],
            'alarm': ['告警', '报警'],
            'temperature': ['温度', '温控'],
            'lock': ['锁', '解锁'],
            'unlock': ['解锁', '开锁'],
            'location': ['定位', '位置'],
            'gps': ['GPS', '定位'],
        }

        for tech_term, biz_terms in term_mapping.items():
            if tech_term in code_lower:
                terms.extend(biz_terms)

        return list(set(terms))[:5]

    def _extract_states_fallback(self, code: str) -> List[str]:
        states = []
        case_matches = re.findall(r'case\s+(\w+)\s*:', code)
        states.extend(case_matches)
        return list(set(states))[:10]

    def apply_semantic_replacement(self, content: str) -> str:
        sanitized = content

        for code_name, (short_desc, full_desc) in CODE_TO_BUSINESS_MAP.items():
            sanitized = re.sub(rf'\b{code_name}\b', short_desc, sanitized)
            sanitized = re.sub(rf'{code_name}\s*=\s*0x[0-9A-Fa-f]+', f'{short_desc}', sanitized)
            sanitized = re.sub(rf'{code_name}\s*=\s*\d+', f'{short_desc}', sanitized)

        sanitized = re.sub(r'//.*$', '', sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r'/\*.*?\*/', '', sanitized, flags=re.DOTALL)
        sanitized = re.sub(r'\bif\s*\(', 'if(', sanitized)
        sanitized = re.sub(r'\belse\s+if\s*\(', 'else if(', sanitized)
        sanitized = re.sub(r'\s+', ' ', sanitized)

        return sanitized

    def distill_code_block(self, code: str, code_type: str, name: str = "") -> DistilledKnowledge:
        if code_type == "function":
            distilled = self.distill_function(code, name)
        elif code_type == "state_machine":
            distilled = self.distill_state_machine(code, name)
        else:
            distilled = self._fallback_distill(code, code_type)

        business_desc = distilled.get('business_logic', '') if isinstance(distilled, dict) else str(distilled)

        keywords = distilled.get('business_terms', []) if isinstance(distilled, dict) else []

        leakage_score = self.calculate_leakage_score(business_desc)
        if leakage_score > 2:
            business_desc = self._sanitize_leakage(business_desc)

        return DistilledKnowledge(
            node_id=name or f"{code_type}_{hash(code)[:8]}",
            node_type=code_type,
            original_code=code,
            distilled_content=json.dumps(distilled, ensure_ascii=False),
            business_description=business_desc,
            keywords=keywords,
            metadata={
                'functionality': distilled.get('functionality', '') if isinstance(distilled, dict) else '',
                'key_conditions': distilled.get('key_conditions', []) if isinstance(distilled, dict) else [],
                'leakage_score': leakage_score
            }
        )

    def calculate_leakage_score(self, content: str) -> int:
        score = 0
        for pattern in LEAKAGE_INDICATORS:
            score += len(re.findall(pattern, content))
        return score

    def _sanitize_leakage(self, content: str) -> str:
        sanitized = content
        sanitized = re.sub(r'0x[0-9A-Fa-f]+', '[HEX]', sanitized)
        sanitized = re.sub(r'\b\w+_t\b', '[TYPE]', sanitized)
        sanitized = re.sub(r'->', '.', sanitized)
        sanitized = re.sub(r'\[\s*\w+\s*\]', '[INDEX]', sanitized)
        return sanitized

    def replace_with_uuids(self, code: str, symbol_map: Dict[str, str]) -> Tuple[str, Dict[str, str]]:
        uuid_map = {}
        sanitized_code = code
        for var_name, semantics in symbol_map.items():
            uid = f"VAR_{uuid.uuid4().hex[:8]}"
            uuid_map[uid] = semantics
            sanitized_code = re.sub(rf'\b{var_name}\b', uid, sanitized_code)
        return sanitized_code, uuid_map

    def _generate_logic_from_template(self, code: str, code_type: str) -> str:
        code_lower = code.lower()
        if 'if(' in code:
            condition_match = re.search(r'if\s*\(\s*(\w+)\s*([><=!]+)\s*(\w+)\s*\)', code)
            if condition_match:
                var, op, val = condition_match.groups()
                return IF_TEMPLATE.format(condition=f"{var}{op}{val}", action="相应业务动作")
        if 'switch' in code_lower:
            var_match = re.search(r'switch\s*\(\s*(\w+)\s*\)', code)
            if var_match:
                return SWITCH_TEMPLATE.format(variable=var_match.group(1))
        if 'while' in code_lower:
            return WHILE_TEMPLATE.format(condition="条件", action="持续操作")
        return "业务逻辑处理"


class KnowledgeGraphStore:
    def __init__(self, db_path: str = "data/knowledge_graph.db"):
        import sqlite3
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        import sqlite3
        import os
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS code_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    distilled_logic TEXT,
                    business_description TEXT,
                    keywords TEXT,
                    module_name TEXT,
                    file_path TEXT,
                    line_number INTEGER,
                    metadata TEXT
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS code_edges (
                    edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_node TEXT NOT NULL,
                    to_node TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    description TEXT,
                    FOREIGN KEY (from_node) REFERENCES code_nodes(node_id),
                    FOREIGN KEY (to_node) REFERENCES code_nodes(node_id)
                )
            ''')

            conn.execute('''
                CREATE TABLE IF NOT EXISTS code_references (
                    ref_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT NOT NULL,
                    original_code TEXT,
                    vector_id TEXT,
                    FOREIGN KEY (node_id) REFERENCES code_nodes(node_id)
                )
            ''')

            conn.execute('CREATE INDEX IF NOT EXISTS idx_edges_from ON code_edges(from_node)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_edges_to ON code_edges(to_node)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_node_type ON code_nodes(node_type)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_keywords ON code_nodes(keywords)')

    def add_node(self, node: DistilledKnowledge, module_name: str = "", file_path: str = "", line_number: int = 0) -> bool:
        import sqlite3
        import json

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT OR REPLACE INTO code_nodes
                    (node_id, node_type, name, distilled_logic, business_description, keywords, module_name, file_path, line_number, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    node.node_id,
                    node.node_type,
                    node.node_id,
                    node.distilled_content,
                    node.business_description,
                    ','.join(node.keywords),
                    module_name,
                    file_path,
                    line_number,
                    json.dumps(node.metadata, ensure_ascii=False)
                ))
            return True
        except Exception as e:
            print(f"Error adding node: {e}")
            return False

    def add_edge(self, from_node: str, to_node: str, edge_type: str, description: str = "") -> bool:
        import sqlite3

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO code_edges (from_node, to_node, edge_type, description)
                    VALUES (?, ?, ?, ?)
                ''', (from_node, to_node, edge_type, description))
            return True
        except Exception as e:
            print(f"Error adding edge: {e}")
            return False

    def get_node(self, node_id: str) -> Optional[Dict]:
        import sqlite3
        import json

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT * FROM code_nodes WHERE node_id = ?', (node_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        'node_id': row[0],
                        'node_type': row[1],
                        'name': row[2],
                        'distilled_logic': row[3],
                        'business_description': row[4],
                        'keywords': row[5].split(',') if row[5] else [],
                        'module_name': row[6],
                        'file_path': row[7],
                        'line_number': row[8],
                        'metadata': json.loads(row[9]) if row[9] else {}
                    }
        except Exception as e:
            print(f"Error getting node: {e}")
        return None

    def get_related_nodes(self, node_id: str, edge_type: str = None, depth: int = 1) -> List[Dict]:
        import sqlite3
        import json

        related = []
        visited = {node_id}
        current_level = {node_id}

        for _ in range(depth):
            next_level = set()
            placeholders = ','.join(['?'] * len(current_level))

            query = f'''
                SELECT DISTINCT n.*, e.edge_type, e.description
                FROM code_nodes n
                JOIN code_edges e ON (e.to_node = n.node_id OR e.from_node = n.node_id)
                WHERE (e.from_node IN ({placeholders}) OR e.to_node IN ({placeholders}))
            '''
            params = list(current_level) * 2

            if edge_type:
                query += ' AND e.edge_type = ?'
                params.append(edge_type)

            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(query, params)
                for row in cursor.fetchall():
                    related_node_id = row[0]
                    if related_node_id not in visited:
                        visited.add(related_node_id)
                        next_level.add(related_node_id)
                        related.append({
                            'node_id': row[0],
                            'node_type': row[1],
                            'name': row[2],
                            'distilled_logic': row[3],
                            'business_description': row[4],
                            'keywords': row[5].split(',') if row[5] else [],
                            'edge_type': row[10],
                            'edge_description': row[11]
                        })

            current_level = next_level
            if not current_level:
                break

        return related

    def search_by_keyword(self, keyword: str, limit: int = 10) -> List[Dict]:
        import sqlite3
        import json

        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT * FROM code_nodes
                    WHERE keywords LIKE ? OR business_description LIKE ?
                    LIMIT ?
                ''', (f'%{keyword}%', f'%{keyword}%', limit))

                results = []
                for row in cursor.fetchall():
                    results.append({
                        'node_id': row[0],
                        'node_type': row[1],
                        'name': row[2],
                        'distilled_logic': row[3],
                        'business_description': row[4],
                        'keywords': row[5].split(',') if row[5] else [],
                        'module_name': row[6],
                        'file_path': row[7]
                    })
                return results
        except Exception as e:
            print(f"Error searching: {e}")
            return []

    def get_call_chain_description(self, start_node: str, max_depth: int = 3) -> str:
        visited = set()
        chain = []

        def dfs(node_id: str, depth: int, path: list):
            if depth >= max_depth or node_id in visited:
                return
            visited.add(node_id)

            node = self.get_node(node_id)
            if node:
                path.append(node['business_description'] or node['name'])

                edges_query = '''
                    SELECT to_node, description FROM code_edges
                    WHERE from_node = ? AND edge_type = 'calls'
                '''
                import sqlite3
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(edges_query, (node_id,))
                    for row in cursor.fetchall():
                        dfs(row[0], depth + 1, path)

        dfs(start_node, 0, chain)

        if chain:
            return " → ".join(chain)
        return "调用链描述不可用"


class DomainKnowledgeBase:
    _instance = None

    def __new__(cls, db_path: str = "data/domain_kb.db"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = "data/domain_kb.db"):
        if self._initialized:
            return
        import sqlite3
        import os
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_db()
        self._merge_static_map()
        self._initialized = True

    def _init_db(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS domain_terms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    term_key TEXT UNIQUE NOT NULL,
                    short_desc TEXT NOT NULL,
                    full_desc TEXT,
                    source TEXT DEFAULT 'manual',
                    category TEXT,
                    dp_id TEXT,
                    created_at TEXT NOT NULL
                )
            ''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_term_key ON domain_terms(term_key)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_dp_id ON domain_terms(dp_id)')

    def _merge_static_map(self):
        import sqlite3
        from datetime import datetime
        for key, (short, full) in CODE_TO_BUSINESS_MAP.items():
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT id FROM domain_terms WHERE term_key = ?', (key,))
                if not cursor.fetchone():
                    conn.execute('''
                        INSERT INTO domain_terms (term_key, short_desc, full_desc, source, created_at)
                        VALUES (?, ?, ?, 'static_map', ?)
                    ''', (key, short, full, datetime.now().isoformat()))

    def add_term(self, term_key: str, short_desc: str, full_desc: str = "", source: str = "manual", category: str = "", dp_id: str = ""):
        import sqlite3
        from datetime import datetime
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                INSERT OR REPLACE INTO domain_terms (term_key, short_desc, full_desc, source, category, dp_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (term_key, short_desc, full_desc, source, category, dp_id, datetime.now().isoformat()))

    def add_dp_term(self, dp_id: str, dp_name: str, dp_desc: str = ""):
        self.add_term(f"DPID_{dp_id}", dp_name, dp_desc, source="protocol_dp", category="datapoint", dp_id=dp_id)

    def get_term(self, term_key: str) -> Optional[Dict]:
        import sqlite3
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT * FROM domain_terms WHERE term_key = ?', (term_key,))
                row = cursor.fetchone()
                if row:
                    return {
                        'term_key': row[1],
                        'short_desc': row[2],
                        'full_desc': row[3],
                        'source': row[4],
                        'category': row[5],
                        'dp_id': row[6]
                    }
        except Exception as e:
            print(f"Error getting term: {e}")
        return None

    def get_all_terms(self) -> Dict[str, Tuple[str, str]]:
        import sqlite3
        result = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('SELECT term_key, short_desc, full_desc FROM domain_terms')
                for row in cursor.fetchall():
                    result[row[0]] = (row[1], row[2] or row[1])
        except Exception as e:
            print(f"Error getting all terms: {e}")
        return result

    def extract_terms_from_text(self, text: str, dp_pattern: str = r"DP(\d+)") -> List[Dict]:
        terms = []
        dp_matches = re.findall(dp_pattern, text)
        for dp_id in dp_matches:
            term = self.get_term(f"DPID_{dp_id}")
            if term:
                terms.append(term)
        return terms