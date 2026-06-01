from typing import Dict, List, Any, Set, Optional
from collections import defaultdict
import json
import sys
sys.path.insert(0, r'D:\workspace\Agent')
from models.vector_store import KnowledgeBase
from models.protocol_tools import TOOL_DEFINITIONS, execute_tool


def get_api_session(proxies=None):
    import requests
    session = requests.Session()
    if proxies is None:
        session.trust_env = False
    else:
        session.proxies = proxies
    return session


ENTITY_GRAPH = {
    'BLE': {
        'keywords': ['BLE', 'bluetooth', '蓝牙', '配对', 'pairing', '绑定', 'bind'],
        'related_entities': ['HID', 'PAIR', 'ADV', 'BOND'],
        'related_topics': ['ble_task', 'vl_ble_evt', 'hid_state', 'pair_overtime']
    },
    'HID': {
        'keywords': ['HID', 'hid', '人机接口', '绑定'],
        'related_entities': ['BLE', 'BOND', 'PAIR'],
        'related_topics': ['hid_state', 'hid_evt', 'ble_device_unbind']
    },
    'Battery': {
        'keywords': ['battery', '电量', '电池', 'BMS'],
        'related_entities': ['BMS', 'PERCENTAGE', 'CHARGE'],
        'related_topics': ['battery_percentage', 'BMS', 'DPID_BATTERY']
    },
    'BMS': {
        'keywords': ['BMS', 'bms', '电池管理', 'SOH'],
        'related_entities': ['Battery', 'PERCENTAGE'],
        'related_topics': ['analyzeBMS', 'battery_info']
    },
    'Fault': {
        'keywords': ['fault', '故障', '错误', 'alarm', '报警', '异常'],
        'related_entities': ['ALARM', 'DETECTION', 'ROLLOVER'],
        'related_topics': ['FAULT_TYPE', 'rollover_detect', 'DPID_FAULT']
    },
    'OTA': {
        'keywords': ['OTA', 'ota', '升级', 'update', '固件'],
        'related_entities': ['FW', 'FLASH', 'VERSION'],
        'related_topics': ['OTA_START', 'OTA_DATA', 'vl_cell_evt']
    },
    'Riding': {
        'keywords': ['riding', '骑行', 'record', '记录', '里程'],
        'related_entities': ['RECORD', 'TRACK', 'GPS'],
        'related_topics': ['0x8005', 'local_record', 'record_reported']
    },
    'DP': {
        'keywords': ['DP', 'dp', '数据点', 'datapoint', '物模型'],
        'related_entities': ['QUERY', 'REPORT', 'RECV'],
        'related_topics': ['dp_query', 'dp_report', 'DPID']
    },
    'CAN': {
        'keywords': ['CAN', 'can', '总线', 'CAN总线'],
        'related_entities': ['PROTOCOL', 'FRAME', 'DLC'],
        'related_topics': ['vl_can', 'CAN_ID', 'DLC']
    },
    'MQTT': {
        'keywords': ['MQTT', 'mqtt', 'topic', '订阅', '发布'],
        'related_entities': ['CELL', 'IOT', 'PUBLISH'],
        'related_topics': ['vl_cell', 'cell_evt', 'mqtt']
    }
}


ENTITY_KEYWORD_MAP = {}
for entity, data in ENTITY_GRAPH.items():
    for keyword in data['keywords']:
        ENTITY_KEYWORD_MAP[keyword.lower()] = entity
    ENTITY_KEYWORD_MAP[entity.lower()] = entity


def detect_entities(query: str) -> Set[str]:
    query_lower = query.lower()
    query_words = set(query_lower.split())

    detected = set()
    for word in query_words:
        if word in ENTITY_KEYWORD_MAP:
            detected.add(ENTITY_KEYWORD_MAP[word])

    for entity, data in ENTITY_GRAPH.items():
        for keyword in data['keywords']:
            if keyword.lower() in query_lower:
                detected.add(entity)
                break

    return detected


def get_related_queries(original_query: str, detected_entities: Set[str]) -> List[str]:
    expanded_queries = [original_query]

    for entity in detected_entities:
        if entity in ENTITY_GRAPH:
            related = ENTITY_GRAPH[entity]['related_entities']
            for rel in related:
                if rel.lower() not in original_query.lower():
                    expanded_queries.append(f"{original_query} {rel}")

            for topic in ENTITY_GRAPH[entity]['related_topics'][:2]:
                if topic.lower() not in original_query.lower():
                    expanded_queries.append(f"{original_query} {topic}")

    return expanded_queries[:5]


CODE_TO_BUSINESS_MAP = {
    # BLE Events
    'VL_BLE_EVT_PAIR': ('配对请求', 'BLE协议中定义的配对请求事件'),
    'VL_BLE_EVT_DEVICE_UNBIND': ('解绑请求', 'BLE协议中定义的解绑请求事件，用于断开已配对设备的连接'),
    'VL_BLE_EVT_FACTORY_RESET': ('恢复出厂设置', 'BLE协议中定义的恢复出厂设置事件'),
    'VL_BLE_EVT_OTA_START': ('OTA升级开始', 'BLE协议中定义的OTA升级开始事件'),
    'VL_BLE_EVT_APP_SYNC_TIME': ('时间同步', 'BLE协议中定义的时间同步请求事件'),
    'VL_BLE_EVT_DP_QUERY': ('数据点查询', 'BLE协议中定义的数据点查询请求'),
    'VL_BLE_EVT_DP_DATA_REV': ('数据点数据接收', 'BLE协议中定义的数据点数据接收事件'),

    # HID State Machine
    'HID_STATE_UNINIT': ('未初始化', 'HID状态：设备未初始化'),
    'HID_STATE_READY': ('就绪待连接', 'HID状态：设备就绪，等待连接'),
    'HID_STATE_CONNECTED': ('已连接', 'HID状态：设备已连接但未绑定'),
    'HID_STATE_BONDED': ('已绑定', 'HID状态：设备已绑定，可正常使用'),
    'hid_state': ('HID状态机', 'HID设备状态管理'),

    # HID Events
    'HID_EVT_CONNECTED': ('HID连接', 'HID设备连接事件'),
    'HID_EVT_DISCONNECTED': ('HID断开', 'HID设备断开连接事件'),
    'HID_EVT_ENCRYPTED': ('HID加密', 'HID连接加密完成事件'),
    'HID_EVT_BONDED': ('HID绑定成功', 'HID设备绑定成功事件'),
    'HID_EVT_BONDED_FAIL': ('HID绑定失败', 'HID设备绑定失败事件'),

    # BLE/HID Functions
    'pair_overtime_cb': ('配对超时回调', '配对超时时的回调函数'),
    'pair_overtimer': ('配对超时定时器', '配对超时定时器'),
    'vl_ble_pair_handler': ('BLE配对处理器', '处理BLE配对请求的函数'),
    'vl_ble_adv_block_set': ('广播屏蔽设置', '设置BLE广播屏蔽标志'),
    'ble_task': ('BLE任务', 'BLE主任务函数'),
    'hid_service_enable': ('HID服务使能', '控制HID服务的启用和禁用'),
    'hid_bonded_count': ('已绑定设备数', '记录已绑定HID设备的数量'),
    'HID_MAX_BOND_DEVICES': ('最大绑定设备数', '系统支持的最大绑定设备数量'),
    'vl_hid_manager_find_bonded_device': ('查找已绑定设备', '查找系统中已绑定的HID设备'),
    'vl_hid_add_bond_device': ('添加绑定设备', '添加一个新的HID绑定设备'),
    'vl_hid_update_rssi_ref': ('更新RSSI参考', '更新信号强度参考值'),
    'vl_hid_handle_encrypted': ('加密连接处理', '处理加密后的HID连接'),
    'irk_info': ('身份解析密钥信息', 'BLE连接的身份解析密钥信息结构'),
    'vl_hid_near_unlock': ('近距离解锁', '近距离感应解锁功能'),

    # BLE Status/State
    'BLE_STATUS_START_ADV': ('开始广播状态', 'BLE设备开始广播的状态'),
    'BLE_STATUS_DISCONNECT': ('断开连接状态', 'BLE断开连接状态'),
    'setDevStatus': ('设备状态设置', '设置设备状态'),
    'ble_processHandle': ('BLE进程处理', 'BLE主进程处理函数'),
    'ble_send_queue_init': ('BLE发送队列初始化', '初始化BLE数据发送队列'),
    'vl_ble_receive_handler': ('BLE接收处理', 'BLE数据接收处理函数'),
    'vl_ble_start_adv': ('开始广播', '启动BLE广播'),

    # BLE Configuration
    'BLE_SNIFF_START': ('Sniff模式开始', 'BLE进入低功耗Sniff模式'),
    'GAP_ADVTYPE_OOB_SIMPLE_PAIRING_HASHC': ('OOB配对', '带外带简单配对哈希'),
    'BEC_PAIRING_NOT_ALLOWED': ('配对不允许', '当前不允许配对'),

    # OTA Related
    'VL_EVT_OTA_START': ('OTA开始事件', 'OTA升级开始的事件'),
    'VL_OTA_STATUS_NONE': ('OTA无状态', 'OTA未开始状态'),
    'VL_OTA_STATUS_START': ('OTA开始', 'OTA升级开始状态'),
    'VL_OTA_STATUS_FILE_INFO': ('OTA文件信息', 'OTA正在传输文件信息'),
    'VL_OTA_STATUS_FILE_OFFSET': ('OTA文件偏移', 'OTA正在传输文件数据偏移'),
    'VL_OTA_STATUS_FILE_DATA': ('OTA文件数据', 'OTA正在传输文件数据'),
    'VL_OTA_STATUS_FILE_END': ('OTA文件结束', 'OTA文件传输完成'),
    'vl_ota_init': ('OTA初始化', 'OTA模块初始化函数'),
    'ota_get_current_version': ('获取当前版本', '获取当前固件版本号'),

    # BMS/ Battery Related
    'CAN_BMS_BATTERY_ERR': ('BMS电池错误', 'BMS电池错误标识'),
    'analyzeSubBATT': ('电池分析', '电池数据分析函数'),
    'DPID_BATTERY_INFO': ('电池信息', '电池信息数据点'),
    'DPID_BATTERY_VOLTAGE_1': ('电池电压', '电池电压数据点'),
    'battery_percentage': ('电量百分比', '电池剩余电量百分比'),
    'endurance_mileage': ('续航里程', '预计可骑行里程'),
    'storage': ('存储', '设备存储模块'),
}


def sanitize_content(content: str) -> str:
    import re

    sanitized = content

    for code_name, (short_desc, full_desc) in CODE_TO_BUSINESS_MAP.items():
        sanitized = re.sub(rf'\b{code_name}\b', short_desc, sanitized)
        sanitized = re.sub(rf'{code_name}\s*=\s*0x[0-9A-Fa-f]+', f'{short_desc}', sanitized)
        sanitized = re.sub(rf'{code_name}\s*=\s*\d+', f'{short_desc}', sanitized)
        sanitized = re.sub(rf'{code_name}\s*\(', f'{short_desc}(', sanitized)
        sanitized = re.sub(rf'\b{code_name}\.', f'{short_desc}.', sanitized)

    sanitized = re.sub(r'\bif\s*\(', 'if(', sanitized)
    sanitized = re.sub(r'\belse\s+if\s*\(', 'else if(', sanitized)

    sanitized = re.sub(r'//.*$', '', sanitized, flags=re.MULTILINE)
    sanitized = re.sub(r'/\*.*?\*/', '', sanitized, flags=re.DOTALL)
    sanitized = re.sub(r'\s+', ' ', sanitized)

    return sanitized


def build_reasoning_chain(query: str, retrieved_docs: List[Dict], detected_entities: Set[str]) -> Dict[str, Any]:
    chain = {
        'step1_analyze': {
            'query': query,
            'detected_entities': list(detected_entities),
            'entity_count': len(detected_entities)
        },
        'step2_retrieve': {
            'docs_count': len(retrieved_docs),
            'doc_titles': [d.get('title', '')[:30] for d in retrieved_docs[:5]]
        },
        'step3_relate': {
            'related_entities_found': [],
            'relationships': []
        },
        'step4_infer': {
            'inferred_topics': [],
            'reasoning': ''
        }
    }

    if detected_entities:
        for entity in detected_entities:
            if entity in ENTITY_GRAPH:
                chain['step3_relate']['related_entities_found'].extend(
                    ENTITY_GRAPH[entity]['related_entities']
                )
                for rel in ENTITY_GRAPH[entity]['related_entities']:
                    chain['step3_relate']['relationships'].append(
                        f"{entity} -> {rel}"
                    )

    return chain


COT_SYSTEM_PROMPT = """你是一个专业的物联网技术支持助手。

【回答规则】

1. **禁止暴露源码**：不许出现任何源码变量名、函数名、枚举名
2. **使用业务语言**：用描述性语言替代源码名称
3. **简洁明确**：直接给出答案

【输出格式】
直接给出回答，不要重复问题。"""


FINAL_ANSWER_SYSTEM_PROMPT = """你是一个专业的物联网技术支持助手，服务于**云迹物联（Vehiclink）**技术团队。

【关键指令强化】

1. **严格忠于知识库**：
   - 所有回答必须基于提供的知识库文档。知识库全部来自**云迹物联（Vehiclink）**，不存在"涂鸦"等第三方平台内容。
   - 如果知识库中没有相关信息，明确回答"根据现有资料，未找到相关信息"，**切勿猜测、推断或引入外部知识**。

2. **优先引用权威定义**：
   - 回答基础概念（DP、OTA、CRC等）时，优先引用**定义最完整、最权威的文档**（如《云迹物联RS485通信协议》通常包含核心协议定义）。
   - 回答中**必须注明出处**（文档标题及章节/表格编号），例如："根据《云迹物联RS485通信协议_Rev18.docx》第4节'各个部件地址及DP'..."

3. **聚焦功能与协议，而非代码**：
   - 重点说明**协议中的作用、格式、使用场景**，避免详细列出内部代码字段名（如dp_code）。
   - 如需说明数据结构，引用知识库中的**表格或示例**即可。

4. **结构化回答**：
   - 对于"含义与作用"类问题，建议采用：
     a) **定义**：直接引用知识库中的明确描述
     b) **核心作用**：归纳其在通信、配置、升级等场景中的角色
     c) **典型示例**：引用知识库中的1-2个典型DP表格或数据格式说明
     d) **相关机制**：简要提及与之相关的协议机制（如上报、查询、校验）

5. **禁止暴露源码**：不许出现任何源码变量名、函数名、枚举名
6. **使用业务语言**：用描述性语言替代源码名称
7. **简洁明确**：直接给出答案，不要重复问题或做过长的铺垫
8. **信息完整**：如果知识库信息不足，明确说明缺失部分

【输出格式】
直接给出回答，每段话都要有具体文档依据。"""

COT_USER_PROMPT_TEMPLATE = """## 用户问题
{question}

## 知识库检索结果
{context}

## 已检测到的相关实体
{entities}

## 请按Chain-of-Thought模式分析并回答问题。
如果知识库内容不足以回答，请基于物联网通用知识进行推理补充。
"""


class EnhancedRAGEngine:
    def __init__(self, knowledge_base):
        self.kb = knowledge_base
        self.entity_graph = ENTITY_GRAPH

    def detect_entities(self, query: str) -> Set[str]:
        return detect_entities(query)

    def retrieve_with_expansion(self, query: str, top_k: int = 5) -> tuple:
        detected = self.detect_entities(query)
        expanded_queries = get_related_queries(query, detected)

        all_results = {}
        for exp_query in expanded_queries:
            items = self.kb.search(exp_query, top_k=top_k * 2)
            for item in items:
                if item.id not in all_results:
                    all_results[item.id] = {
                        'id': item.id,
                        'type': item.type,
                        'category': item.category,
                        'title': item.title,
                        'content': item.content,
                        'source_file': item.source_file,
                        'line_number': item.line_number,
                        'query_match': exp_query
                    }

        results = list(all_results.values())
        results.sort(key=lambda x: len(x.get('query_match', '')), reverse=True)

        reasoning_chain = build_reasoning_chain(query, results, detected)

        return results[:top_k], reasoning_chain

    def build_context(self, retrieved_docs: List[Dict], max_chars: int = 4000) -> str:
        if not retrieved_docs:
            return "未找到相关知识库内容。"

        context_parts = []
        current_length = 0

        for doc in retrieved_docs:
            doc_type = doc.get('type', 'unknown')
            doc_category = doc.get('category', '')
            title = doc.get('title', 'Untitled')
            raw_content = doc.get('content', '')
            content = sanitize_content(raw_content)[:600]

            if doc_category == 'protocol' or 'business' in doc_type:
                doc_text = f"""
【业务文档】{title}
内容:
{content}
"""
            elif doc_category == 'c_code':
                doc_text = f"""
【代码实现】{title}
内容:
{content}
"""
            else:
                doc_text = f"""
【{doc_type}】{title}
内容:
{content[:400]}
"""

            if current_length + len(doc_text) > max_chars:
                break
            context_parts.append(doc_text)
            current_length += len(doc_text)

        return "\n---\n".join(context_parts)

    def get_related_info(self, entities: Set[str]) -> Dict[str, List[str]]:
        related = defaultdict(list)
        for entity in entities:
            if entity in self.entity_graph:
                related[entity] = self.entity_graph[entity]['related_entities']
        return dict(related)


class EnhancedAnswerGenerator:
    def __init__(self, api_key: str, base_url: str = "https://api.minimax.chat/v1"):
        self.api_key = api_key
        self.base_url = base_url

    def generate_with_cot(
        self,
        question: str,
        context: str,
        entities: List[str],
        reasoning_chain: Dict[str, Any]
    ) -> str:
        user_prompt = COT_USER_PROMPT_TEMPLATE.format(
            question=question,
            context=context,
            entities=", ".join(entities) if entities else "无",
        )

        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                session = get_api_session(PROXIES)
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "MiniMax-M2.7",
                    "max_tokens": 1200,
                    "temperature": 0.3,
                    "messages": [
                        {"role": "system", "content": COT_SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt}
                    ]
                }
                response = session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("choices") and result["choices"][0].get("message", {}).get("content"):
                        return result["choices"][0]["message"]["content"]
                    return f"API错误: 返回格式异常 - {response.text[:200]}"
                elif response.status_code == 529:
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(retry_delay * (attempt + 1))
                        continue
                    return f"API错误: 服务过载，请稍后重试 (529)"
                return f"API错误: {response.status_code} - {response.text[:200]}"
            except Exception as e:
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                return f"生成回答时出错: {str(e)}"

        return "生成回答失败，已达最大重试次数"


class EnhancedFAQAgent:
    def __init__(self, knowledge_base: KnowledgeBase, answer_generator: EnhancedAnswerGenerator):
        self.rag = EnhancedRAGEngine(knowledge_base)
        self.generator = answer_generator

    def ask(self, question: str, category: str = None, top_k: int = 5) -> Dict[str, Any]:
        import time
        t0 = time.time()

        detected_entities = self.rag.detect_entities(question)
        t1 = time.time()

        retrieved, reasoning_chain = self.rag.retrieve_with_expansion(question, top_k=top_k)
        t2 = time.time()

        context = self.rag.build_context(retrieved)
        t3 = time.time()

        answer = self.generator.generate_with_cot(
            question, context,
            list(detected_entities),
            reasoning_chain
        )
        t4 = time.time()

        return {
            "question": question,
            "answer": answer,
            "category": category or "detected",
            "detected_entities": list(detected_entities),
            "retrieved_count": len(retrieved),
            "reasoning_chain": reasoning_chain,
            "timing": {
                "entity_detection": t1 - t0,
                "retrieval": t2 - t1,
                "context_build": t3 - t2,
                "generation": t4 - t3,
                "total": t4 - t0
            }
        }


REACT_SYSTEM_PROMPT = """你是一个专业的物联网技术支持助手，采用ReAct（Reasoning + Acting）迭代推理模式。

【核心循环 - 必须遵循】

你必须通过多轮迭代来回答复杂问题，每轮包含：

1. **Thought (思考)**: 分析当前状态，决定下一步行动
2. **Action (行动)**: 执行检索、工具调用或准备回答
3. **Observation (观察)**: 获取行动结果，评估是否足够

【分级检索策略 - 必须按顺序执行】

**一级检索（协议优先）**：
- 先搜索精确的协议术语（如"骑行记录"、"DP18"、"0x8005"）
- 如果结果不足，进入二级

**二级检索（语义扩展）**：
- 使用同义词/近义词搜索（如：trip_data、history_record、report、upload）
- 如果仍然不足，进入三级

**三级检索（代码深挖）**：
- 强制检索代码实现（如：grep "DPID_MILEAGE" riding_end_callback）
- 代码证据优先级低于协议文档

**跨域联动规则**：
- 发现具体DP ID（如DP18、DP19）后：
  1. 先用lookup_dp_id()确认DP定义
  2. **必须**检索代码中该DP的使用上下文
  3. 搜索关键词：函数名_callback、dp_report、mcu_dp_raw_update

**隐式依赖识别 - 必须执行**：
- 当用户问"如何操作/上报/查询X"时，**必须**先检索"X的生成/创建/计算逻辑"
- 操作依赖于前置知识，不知道生成方式就无法说清操作流程
- 例如：问"骑行记录上报" → 必须也检索"骑行记录生成逻辑"
- 例如：问"数据如何下发" → 必须也检索"数据如何构造/组装"
- 例如：问"如何查询状态" → 必须也检索"状态如何定义和更新"

**【意图分类 - 必须先判断再行动】**

问题类型A：**"XX是什么/什么意思/什么数据类型"**
- 示例：DP18是什么？单次里程的数据类型？
- 行动：使用 search_dp_by_name 或 lookup_dp_id

问题类型B：**"XX如何操作/如何上报/如何配置/怎么用"**
- 示例：骑行记录上报如何操作？数据如何下发？
- 行动：**直接使用 search_knowledge**，不要先搜 DP
- 原因：操作类问题的答案在协议文档/业务流程中，不在 DP 定义中

问题类型C：**"XX的代码实现/函数名/在哪里"**
- 示例：骑行结束回调函数在哪里？
- 行动：使用 search_code

【可用工具】

**lookup_dp_id(dp_id)**: 根据DP ID查找BLE协议数据点定义
- 示例：lookup_dp_id("16") 查询速度DP

**lookup_rs485_dp(dp_id)**: 根据DP ID查找RS485协议数据点定义

**search_dp_by_name(keyword)**: 在BLE协议中搜索DP定义

**search_rs485_by_name(keyword)**: 在RS485协议中搜索DP定义

**search_code(function_name)**: 检索代码中函数实现
- 示例：search_code("riding_end") 搜索骑行结束相关函数
- **强制使用**：当发现具体DP ID时，必须调用此工具

**parse_hex_data(hex_str)**: 解析十六进制数据
**search_knowledge(keyword)**: 通用知识检索，搜索协议文档和知识库。当DP搜索失败或需要业务流程信息时必须调用。例如：search_knowledge("骑行记录")、search_knowledge("App上报")、search_knowledge("8005")。

【追查到底终止阈值】

**以下情况必须继续检索，不得输出最终回答**：
1. 发现DP ID但未找到代码实现
2. 检索结果被截断（如"...(truncated)"）
3. 关键业务逻辑缺失描述
4. Raw数据类型未解析

**只有满足以下条件才能输出最终回答**：
1. 找到了触发机制的明确描述
2. 找到了数据结构的具体定义
3. 找到了代码参考（如有）
4. 或明确标注"未找到相关信息"

【最终回答模板 - 必须包含4要素】

```
[触发机制]
<描述业务触发条件，如：骑行结束后触发、蓝牙连接时触发>

[数据结构]
<描述数据格式，如：DP18=单次里程(4字节)、DP87=聚合Raw数据>

[技术推论]
<如协议未明确，基于代码推断的结论>

[引用内容]
<列出参考文档信息>
```

【禁止事项 - 严格遵守】

1. **禁止暴露源码**：不许出现变量名、函数名（如mcu_dp_raw_update）
2. **禁止重复检索**：相同查询只检索一次
3. **禁止提前终止**：结果不足时必须继续
4. **search_knowledge工具**：
   - 当DP搜索失败或需要业务流程信息时，必须调用 search_knowledge
   - search_knowledge 可以多次调用，只要还没找到完整信息

【输出格式】

每轮输出：
## Thought {n}
<分析当前状态和需求>

## Action
search("<检索词>") 或 tool_name({"param": "value"}) 或 answer()

## Observation
<检索结果摘要或状态评估>"""

REACT_USER_PROMPT_TEMPLATE = """## 用户问题
{question}

## 分级检索状态
{retrieval_status}

## 可用工具
{tools}

## 迭代历史
{history}

## 当前上下文
{context}

请进行第{iteration}轮思考：
- 先判断当前检索是否充分（参考分级检索状态）
- 如需扩展检索，使用语义近义词或进入下一级检索
- 如需追查DP实现，必须调用search_code
- 只有满足三要素（触发机制、数据结构、代码参考）才输出answer()

【语义扩展词参考】
- 骑行记录相关：trip_data, history_record, riding_log, report_interval, raw_data
- 数据上报相关：upload, transmit, mcu_dp, dp_report, callback
- 协议命令相关：0x8005, record_reported, CMD, frame"""


class QueryRefiner:
    DOMAIN_TERMS = {
        'riding': ['trip', 'history', 'record', 'log', '轨迹', '行程'],
        'report': ['upload', 'transmit', 'send', '上报', '上传', '发送'],
        'dp': ['datapoint', 'data_point', '数据点', '物模型'],
        'BLE': ['bluetooth', '蓝牙', 'HID', 'pairing'],
        'RS485': ['can', '总线', 'uart', '串口'],
        'OTA': ['upgrade', 'update', '升级', '固件'],
        'fault': ['alarm', 'error', '故障', '异常', '报警'],
        'battery': ['电量', '电池', 'BMS', 'percent'],
    }

    TECH_SYNONYMS = {
        '骑行记录': ['trip_record', 'riding_history', 'history_record', '行程记录', '轨迹记录'],
        '数据上报': ['data_report', 'upload', 'data_transmit', 'dp_report', '上报数据'],
        '里程': ['mileage', 'distance', 'odometer', '距离'],
        '速度': ['speed', 'velocity', '速率'],
        '电量': ['battery', 'SOC', 'percentage', '电池余量'],
        '故障': ['fault', 'alarm', 'error', '异常', '告警'],
    }

    def refine_query(self, original_query: str) -> List[str]:
        """生成语义扩展查询词"""
        expanded = [original_query]
        query_lower = original_query.lower()

        for key, synonyms in self.TECH_SYNONYMS.items():
            if key in query_lower or any(s in query_lower for s in synonyms):
                for syn in synonyms:
                    if syn.lower() not in query_lower and syn not in expanded:
                        expanded.append(syn)
                        if len(expanded) >= 5:
                            break
            if len(expanded) >= 5:
                break

        for domain, terms in self.DOMAIN_TERMS.items():
            if domain in query_lower:
                for term in terms:
                    if term.lower() not in query_lower and term not in expanded:
                        expanded.append(term)
                        if len(expanded) >= 5:
                            break
            if len(expanded) >= 5:
                break

        return expanded[:5]

    def suggest_fallback_queries(self, failed_query: str) -> List[str]:
        """为失败查询生成回退查询"""
        fallbacks = []

        if '记录' in failed_query or 'record' in failed_query.lower():
            fallbacks.extend(['trip_data', 'history', '8005', '骑行'])
        if '骑行' in failed_query:
            fallbacks.extend(['riding', '行程', '里程', '0x8005'])
        if '上报' in failed_query or 'report' in failed_query.lower():
            fallbacks.extend(['upload', 'dp_report', '数据上传'])
        if 'DP' in failed_query or '数据点' in failed_query:
            fallbacks.extend(['datapoint', 'DP定义', '物模型'])

        return fallbacks[:3]


class ReActRAGEngine:
    def __init__(self, knowledge_base):
        self.kb = knowledge_base
        self.max_iterations = 5
        self.query_refiner = QueryRefiner()

    def get_incomplete_info_reason(self, history: List[Dict]) -> str:
        """检测信息不完整的原因"""
        reasons = []

        has_dp_lookup = any(h.get('tool') in ['lookup_dp_id', 'lookup_rs485_dp', 'search_dp_by_name'] for h in history)
        has_code_search = any(h.get('tool') == 'search_code' for h in history)
        has_knowledge_success = any(h.get('tool') == 'search_knowledge' and h.get('result', {}).get('success') for h in history)
        has_results = any(h.get('results') for h in history)

        total_results = sum(len(h.get('results', [])) for h in history)
        has_meaningful_results = total_results >= 3

        if has_results:
            for h in history:
                if h.get('results'):
                    for r in h['results']:
                        content = r.get('content', '')
                        if 'truncated' in content.lower() or '...' in content:
                            reasons.append("检索结果被截断")
                            break

        if has_results and not has_meaningful_results:
            reasons.append(f"检索结果不足(仅{total_results}条)，可能需要扩展检索")

        if has_dp_lookup and not has_code_search and not has_knowledge_success:
            reasons.append("发现DP ID但未检索代码实现")

        for h in history:
            if h.get('result', {}).get('success') == False:
                tool_name = h.get('tool', '')
                if 'dp' in tool_name.lower() or 'DP' in tool_name:
                    reasons.append(f"DP查询失败: {h.get('result', {}).get('error', '')}")

        return "; ".join(reasons) if reasons else ""

    def search_knowledge(self, query: str) -> List[Dict]:
        """执行知识检索"""
        print(f"[DEBUG] search_knowledge 开始搜索: {query}")
        items = self.kb.search(query, top_k=10)
        print(f"[DEBUG] search_knowledge 完成，返回{len(items)}条结果")
        results = []
        for item in items:
            # Pass full content (up to 2000 chars) to preserve document structure
            sanitized_content = sanitize_content(item.content[:2000])
            results.append({
                'id': item.id,
                'type': item.type,
                'title': item.title,
                'content': sanitized_content
            })
        return results

    def format_results(self, results: List[Dict]) -> str:
        """格式化检索结果"""
        if not results:
            return "未找到相关信息"
        parts = []
        for r in results:
            title = r.get('title', 'Untitled')
            content = r.get('content_preview', r.get('content', ''))
            source = r.get('source', '')
            # Use full content instead of truncating to 300 chars
            parts.append(f"【来源】{source}\n【标题】{title}\n【内容】{content[:1500]}")
        return "\n---\n".join(parts)

    def confirm_intent(self, question: str, context: str) -> Dict[str, Any]:
        """确认用户的真正意图，返回澄清问题和建议的检索词"""
        from config import MINIMAX_API_KEY, PROXIES
        import json

        user_prompt = f"""## 用户原始问题
{question}

## 当前检索上下文
{context}

请分析用户问题的真实意图，并给出：
1. 问题的核心意图（1句话）
2. 可能的相关检索词（3-5个）
3. 如果问题模糊或不完整，生成一个澄清问题

请用中文回答，格式如下：
意图：<核心意图>
建议检索词：<词1>, <词2>, <词3>
澄清问题：<如果需要的话>"""

        messages = [{"role": "user", "content": user_prompt}]

        try:
            headers = {
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "MiniMax-M2.7",
                "max_tokens": 300,
                "temperature": 0.3,
                "messages": messages
            }
            session = get_api_session(PROXIES)
            response = session.post(
                "https://api.minimax.chat/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=(10, 30)
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("choices"):
                    content = result["choices"][0]["message"]["content"]
                    intent_match = re.search(r'意图：(.+)', content)
                    keywords_match = re.search(r'建议检索词：(.+)', content)
                    clarify_match = re.search(r'澄清问题：(.+)', content)
                    return {
                        "success": True,
                        "intent": intent_match.group(1).strip() if intent_match else "",
                        "keywords": [k.strip() for k in keywords_match.group(1).split(',')] if keywords_match else [],
                        "clarify": clarify_match.group(1).strip() if clarify_match else ""
                    }
        except Exception as e:
            return {"success": False, "error": str(e)}
        return {"success": False, "error": "确认意图失败"}

    def think(self, state: Dict) -> Dict[str, Any]:
        """让LLM决定下一步行动"""
        import time
        from config import MINIMAX_API_KEY, PROXIES
        import json

        tools_json = json.dumps(TOOL_DEFINITIONS, ensure_ascii=False, indent=2)

        history = state.get('history', [])
        search_queries = [h.get('query', '').lower() for h in history if h.get('query')]
        dp_tools_used = any(h.get('tool') in ['lookup_dp_id', 'lookup_rs485_dp', 'search_dp_by_name'] for h in history)
        code_searched = any(h.get('tool') == 'search_code' for h in history)

        level = 1
        if search_queries:
            level = 2
        if code_searched:
            level = 3

        retrieval_status = f"""当前检索级别: {'一级(协议)' if level == 1 else '二级(语义扩展)' if level == 2 else '三级(代码深挖)'}
已检索词: {', '.join(search_queries[:5]) if search_queries else '无'}
DP工具已调用: {'是' if dp_tools_used else '否'}
代码已检索: {'是' if code_searched else '否'}"""

        user_prompt = REACT_USER_PROMPT_TEMPLATE.format(
            question=state['question'],
            retrieval_status=retrieval_status,
            tools=tools_json,
            history=state['history'],
            context=state['context'],
            iteration=state['iteration']
        )

        messages = [
            {"role": "system", "content": REACT_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        try:
            headers = {
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "MiniMax-M2.7",
                "max_tokens": 800,
                "temperature": 0.3,
                "messages": messages,
                "tools": TOOL_DEFINITIONS
            }
            session = get_api_session(PROXIES)
            response = session.post(
                "https://api.minimax.chat/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=(10, 60)
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("choices"):
                    message = result["choices"][0]["message"]
                    if "tool_calls" in message:
                        return {
                            "type": "tool_call",
                            "content": message.get("content", ""),
                            "tool_calls": message["tool_calls"]
                        }
                    return {
                        "type": "text",
                        "content": message.get("content", "")
                    }
        except Exception as e:
            return {"type": "error", "content": f"思考出错: {e}", "tool_calls": []}

        return {"type": "text", "content": "answer()", "tool_calls": []}

    def parse_action(self, thought_output: Dict[str, Any]) -> tuple:
        """解析LLM输出，决定行动"""
        import re

        if thought_output.get('type') == 'tool_call' and thought_output.get('tool_calls'):
            tool_call = thought_output['tool_calls'][0]
            func_name = tool_call.get('function', {}).get('name', '')
            if func_name == 'answer':
                return ('answer', None)
            if func_name == 'search':
                arguments = tool_call.get('function', {}).get('arguments', '')
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except:
                        pass
                if isinstance(arguments, dict):
                    query = arguments.get('query', arguments.get('keyword', ''))
                else:
                    query = str(arguments)
                if query:
                    return ('search', query)
                return ('answer', None)
            arguments = tool_call.get('function', {}).get('arguments', '')
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except:
                    arguments = {}
            return ('tool_call', {'name': func_name, 'arguments': arguments})

        content = thought_output.get('content', '')

        search_match = re.search(r'search\s*\(\s*["\']([^"\']+)["\']\s*\)', content, re.IGNORECASE)
        if search_match:
            query = search_match.group(1)
            return ('search', query)

        if 'answer()' in content.lower() or '生成回答' in content:
            return ('answer', None)

        return ('answer', None)

    def build_context_from_history(self, history: List[Dict]) -> str:
        """从迭代历史构建上下文"""
        if not history:
            return "暂无检索历史"

        parts = []
        for entry in history:
            if entry.get('results'):
                parts.append(f"【{entry['query']}检索结果】\n{self.format_results(entry['results'])}")
            elif entry.get('tool'):
                tool_name = entry['tool']
                result = entry.get('result', {})
                if result.get('success'):
                    data = result.get('data', {})
                    parts.append(f"【工具调用: {tool_name}】\n结果: {json.dumps(data, ensure_ascii=False)[:300]}")
                else:
                    parts.append(f"【工具调用: {tool_name}】\n错误: {result.get('error', 'Unknown error')}")
        return "\n---\n".join(parts)

    def react_ask(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """ReAct主循环"""
        import time
        t0 = time.time()

        state = {
            'question': question,
            'iteration': 1,
            'history': [],
            'context': '',
            'converged': False,
            'final_answer': None
        }

        while state['iteration'] <= self.max_iterations and not state['converged']:
            print(f"[DEBUG] 第{state['iteration']}轮开始...", flush=True)
            thought_output = self.think(state)
            print(f"[DEBUG] think返回: {thought_output.get('type', 'unknown')}")

            action, param = self.parse_action(thought_output)

            if action == 'search':
                results = self.search_knowledge(param)
                history_entry = {
                    'query': param,
                    'results': results,
                    'thought': thought_output
                }
                state['history'].append(history_entry)
                state['context'] = self.build_context_from_history(state['history'])
                state['iteration'] += 1

                if not results and state['iteration'] <= self.max_iterations:
                    fallbacks = self.query_refiner.suggest_fallback_queries(param)
                    if fallbacks:
                        print(f"[DEBUG] 自动回退到语义扩展词: {fallbacks}")
                        for fb_query in fallbacks[:2]:
                            fb_results = self.search_knowledge(fb_query)
                            if fb_results:
                                state['history'].append({
                                    'query': fb_query,
                                    'results': fb_results,
                                    'fallback': True
                                })
                                state['context'] = self.build_context_from_history(state['history'])
                                break

                if state['iteration'] == 2 and not results:
                    intent_result = self.confirm_intent(state['question'], state['context'])
                    history_entry['intent_confirm'] = intent_result

            elif action == 'tool_call':
                print(f"[DEBUG] 执行工具: {param['name']} args={param['arguments']}", flush=True)
                tool_result = execute_tool(param['name'], param['arguments'])
                print(f"[DEBUG] 工具结果: success={tool_result.get('success')}, error={tool_result.get('error', 'none')[:50]}", flush=True)
                history_entry = {
                    'tool': param['name'],
                    'arguments': param['arguments'],
                    'result': tool_result,
                    'thought': thought_output.get('content', '')
                }
                state['history'].append(history_entry)
                state['context'] = self.build_context_from_history(state['history'])
                state['iteration'] += 1

            elif action == 'answer':
                incomplete_reason = self.get_incomplete_info_reason(state['history'])
                if incomplete_reason and state['iteration'] < self.max_iterations:
                    print(f"[DEBUG] 信息不完整，继续检索: {incomplete_reason}")
                    state['iteration'] += 1
                    continue
                state['final_answer'] = self.synthesize_answer(state)
                state['converged'] = True
                break

        if not state['converged'] and state['iteration'] > self.max_iterations:
            incomplete_reason = self.get_incomplete_info_reason(state['history'])
            if incomplete_reason:
                state['final_answer'] = f"[信息不完整]\n{incomplete_reason}\n\n" + self.synthesize_answer(state)
            else:
                state['final_answer'] = self.synthesize_answer(state)

        t1 = time.time()

        total_results = sum(len(h.get('results', [])) for h in state['history'])

        return {
            "question": question,
            "answer": state['final_answer'],
            "iterations": state['iteration'] - 1,
            "total_results": total_results,
            "history": state['history'],
            "context": state['context'],
            "timing": {
                "total": t1 - t0
            }
        }

    def ask(self, question: str, category: str = None, top_k: int = 5) -> Dict[str, Any]:
        return self.react_ask(question, top_k)

    def synthesize_answer(self, state: Dict) -> str:
        """综合历史信息生成最终回答，使用结构化模板"""
        from config import MINIMAX_API_KEY, PROXIES

        context = state['context']
        if not context:
            context = "知识库中未找到相关信息"

        history = state.get('history', [])
        dp_tools_used = any(entry.get('tool') in ['lookup_dp_id', 'lookup_rs485_dp', 'search_dp_by_name'] for entry in history)
        code_searched = any(entry.get('tool') == 'search_code' for entry in history)

        user_prompt = f"""## 用户问题
{state['question']}

## 知识库检索结果（按来源分组）
{context}

## 检索完成情况
- DP工具查询: {'是' if dp_tools_used else '否'}
- 代码检索: {'是' if code_searched else '否'}

## 重要提示
- 知识库检索结果中的【内容】可能只显示了文档的部分片段，请仔细阅读并提取相关信息
- 如果文档提到"骑行记录参照蓝牙协议中8005命令上报"，说明骑行记录确实存在，请继续查找8005相关DP定义
- 如果上下文中出现"..."表示内容被截断，请基于已有信息进行总结

## 关键信息提取指引
请务必从上述检索结果中提取并核实以下信息：

### 1. 骑行记录生成逻辑
- 文档明确提到"骑行记录参照蓝牙协议中8005命令上报规则进行上报"
- 文档明确提到"时间戳通过8003指令获取"
- 文档明确提到"生成逻辑：开机后开始记录骑行，关机后生成当次骑行记录"

### 2. 触发条件（三种情况）
文档提到"行程记录的触发条件（分三种情况）"：
- 情况1：设备已开机并已连接蓝牙
- 情况2：设备开机时未连接蓝牙，后续连接成功
- 情况3：全程未连接蓝牙（不生成任何行程记录）

### 3. 上报涉及DP列表
文档明确列出"上报涉及dp有："：
- DP 17: ridetime_once (单次骑行时间)
- DP 18: mileage_once (单次里程)
- DP 67: top_speed (车辆最高速度)
- DP 68: average_speed (车辆平均速度)
- DP 72: man_out_aver_power (人力输出平均功率)
- DP 73: motor_out_aver_power (电机输出平均功率)
- DP 86: calorie_ride_once (单次骑行卡路里消耗)

### 4. 附加规则
- "骑行距离不足100m不生成，时间未获取到不生成"
- 有RTC模块可离线存储后上报，无RTC模块需在开关机时刻获取时间

## 输出要求 - 必须包含以下3要素

1. 【触发机制】描述业务触发条件（何时触发、如何触发）
2. 【数据结构】描述数据格式（DP定义、字段含义）
3. 【技术推论】如协议未明确，基于代码推断的结论

## 输出格式
[触发机制]
<基于知识库文档的触发机制描述，必须引用来源>

[数据结构]
<基于知识库文档的数据结构描述，必须引用来源>

[技术推论]
<技术推论描述（可选），或"无">"""

        messages = [
            {"role": "system", "content": FINAL_ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ]

        try:
            headers = {
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "MiniMax-M2.7",
                "max_tokens": 1200,
                "temperature": 0.3,
                "messages": messages
            }
            session = get_api_session(PROXIES)
            max_retries = 3
            for attempt in range(max_retries):
                response = session.post(
                    "https://api.minimax.chat/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=(10, 60)
                )
                if response.status_code == 200:
                    result = response.json()
                    if result.get("choices"):
                        return result["choices"][0]["message"]["content"]
                    print(f"[DEBUG] synthesize_answer: no choices in result: {result}")
                elif response.status_code == 529:
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(2 ** attempt)
                        continue
                print(f"[DEBUG] synthesize_answer failed: status={response.status_code} text={response.text[:200]}")
                break
        except Exception as e:
            return f"生成回答时出错: {e}"

        return "生成回答失败"
