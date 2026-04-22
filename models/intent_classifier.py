import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class QuestionIntent:
    category: str
    confidence: float
    keywords_matched: List[str]
    suggested_search: str
    rewritten_query: str = ''
    hypothetical_queries: List[str] = field(default_factory=list)


# 基于知识库的标准术语映射
COLLOQUIAL_TO_TECH_MAP = {
    '那玩意': 'IoT设备',
    '那个': '设备',
    '玩意': '设备',
    '车子': '车辆',
    '车车': '车辆',
    '跌了': '净值回撤',
    '不行': '故障/异常',
    '怎么搞': '处理方法',
    '咋办': '解决方案',
    '有啥': '有哪些',
    '那货': '设备',
    '东东': '设备',
    '最近': '近期',
    # 新增基于知识库的映射
    '蓝牙连接': 'BLE连接',
    '蓝牙配对': 'BLE配对绑定',
    '蓝牙广播': 'BLE广播',
    '蓝牙协议': '云迹物联BLE协议',
    'can协议': 'CAN协议',
    '485协议': 'RS485协议',
    '数据点': 'DP数据点',
    '功能点': 'DP数据点',
    '升级': 'OTA升级',
    '固件升级': 'OTA升级',
    '加密': '安全加密',
    '校验': 'CRC校验',
}

INTENT_ACTION_MAP = {
    '怎么办': ['策略', '建议', '处理', '解决', '方案'],
    '如何': ['方法', '步骤', '实现', '流程'],
    '怎么': ['方式', '方法', '步骤'],
    '为什么': ['原因', '原理'],
    '什么时候': ['时间点', '时机', '条件'],
    # 新增基于知识库的动作映射
    '上报': ['上报机制', '上报格式', '上报流程'],
    '查询': ['查询指令', '查询流程'],
    '下发': ['下发指令', '下发格式'],
    '绑定': ['配对绑定流程'],
    '升级': ['OTA升级流程'],
}

PRONOUN_MAP = {
    '它': '设备',
    '他': '设备',
    '她': '设备',
    '这个': '该',
    '那个': '该',
    '这些': '这些',
    '那些': '那些',
}


class IntentClassifier:
    # 基于知识库内容优化的分类模式
    CATEGORY_PATTERNS = {
        'bluetooth': {
            'keywords': [
                # 基础术语
                '蓝牙', 'ble', 'bluetooth', '广播', '连接', '配对', 'gatt', 'characteristic',
                'service', 'uuid', 'device', 'peripheral', 'central', 'advertising',
                'app', '同步', '骑行记录', 'dp_query', 'dp数据', 'ble事件', 'BLE事件',
                '状态查询', 'app同步', '解锁', '靠近解锁', 'HID', 'ATT', 'GATT',
                # 知识库特定术语
                '云迹物联', 'vehiclink', '配对绑定', '安全加密', '异或加密', '会话密钥',
                '功能码', '0x0000', '0x0001', '0x0002', '0x0003', '0x0005', '0x0006',
                '0x000C', '0x000D', '0x000E', '0x001A', '0x001B', '0x001C',
                '0x0010', '0x0011', '0x0012', '0x0014', '0x0025',
                '0x8001', '0x8002', '0x8003', '0x8005',
                'SN', 'ACK_SN', 'CRC16', '数据长度', '帧格式',
                'dp_id', 'dp_type', 'dp_data_len', 'dp_data_value',
                '实时上报', '带时间戳上报', '响应帧', '命令帧',
            ],
            'patterns': [
                r'蓝牙.*?(协议|帧|格式|交互|加密|配对)',
                r'BLE.*?(frame|protocol|packet|功能码|指令)',
                r'0x[0-9A-Fa-f]{2,4}.*?(蓝牙|ble|BLE)',
                r'app.*?(同步|连接|配对|绑定)',
                r'骑行记录.*?(上报|查询)',
                r'.*?(dp|DP).*?(query|Query|查询|上报|下发)',
                r'功能码.*?0x[0-9A-Fa-f]{4}',
                r'(SN|ACK_SN|CRC16).*?(格式|计算)',
                r'数据点.*?(上报|格式|定义)',
                r'OTA.*?(升级|开始|结束|进度)',
            ]
        },
        'can': {
            'keywords': [
                # 基础术语
                'can', 'canbus', 'can总线', 'canopen', '帧id', 'frame.?id', 'dlc',
                '数据帧', '远程帧', '错误帧', 'arbitration', '优先级', '波特率',
                'CAN指令', 'can指令', '报文', 'pgn', 'PGN',
                # 知识库特定术语
                'E-bike Smart CAN协议', 'Smart协议', 'V1.0.29',
                '扩展帧', '标准帧', '250Kbps', '小端模式',
                'PDU1', 'PDU2', '源地址', '目的地址',
                '0x00FE02', '0x00FE20', '0x00FF0A', '0x00FF30',
                '控制器状态', 'BMS信息', '仪表信息', 'IoT信息',
                '增量信号', '整合协议', 'CAN61协议',
                '电机控制模式', '油门模式', '转矩模式', '转速模式',
                '边撑状态', '主继电器状态', '相电流', '电机圈数',
            ],
            'patterns': [
                r'CAN.*?(协议|帧|格式|交互|指令|状态)',
                r'.*?(帧ID|ID|PGN).*?(0x[0-9A-Fa-f]+|CAN)',
                r'0x[0-9A-Fa-f]{3,8}.*?(can|CAN|PGN)',
                r'.*?(指令|命令|控制).*?(CAN|can)',
                r'Smart协议.*?(整合|增量|定义)',
                r'BMS.*?(信息|状态|参数)',
                r'控制器.*?(状态|故障|模式)',
                r'OTA.*?(CAN|升级)',
            ]
        },
        'rs485': {
            'keywords': [
                '485', 'rs485', 'RS485', '串口', 'uart', '主从',
                '轮询', '请求应答', '一主多从', '匹配电阻', '120Ω',
                '波特率115200', '8N1', '功能码', '0x03', '0x04', '0x83', '0x96',
                '异常响应', 'CRC16校验', '地址映射', 'DP表',
                'MCU地址', '仪表地址', 'BMS地址', 'IoT地址',
                '0x01', '0x02', '0x03', '0x04',
                'DP地址', '10041', '20042', '30043', '43081',
                '数据映射', '基于DP的数据映射',
            ],
            'patterns': [
                r'485.*?(协议|通信|格式|交互)',
                r'RS485.*?(主从|轮询|请求应答)',
                r'功能码.*?(0x03|0x04|0x83|0x96)',
                r'DP.*?(表|地址|映射)',
                r'地址.*?(0x[0-9A-Fa-f]{1,2}|MCU|仪表|BMS|IoT)',
                r'异常响应.*?(代码|格式)',
                r'CRC16.*?(校验|计算)',
            ]
        },
        'dp': {
            'keywords': [
                'dp', 'data.?point', '物模型', '数据点', '属性', 'property', 'event',
                'action', '功能', '类型', '布尔', '数值', '字符串', '枚举',
                'dp点', '功能点', 'dp_id', 'dpid', 'dp_type', 'dp_data',
                'dp_data_len', 'dp_data_value', '数据长度', '数据值',
                '实时状态', '历史状态', '时间戳', '上报机制',
                '查询指令', '下发指令', '配置参数', '调试',
            ],
            'patterns': [
                r'dp[_\s]*\d+',
                r'数据点.*?(定义|格式|类型|上报|查询)',
                r'0x[0-9A-Fa-f]{2,}.*?(dp|数据点)',
                r'dp_id.*?\d+',
                r'dp_type.*?(RAW|BOOL|VALUE|STRING|ENUM|BITMAP)',
                r'上报.*?(实时|带时间戳|历史)',
                r'物模型.*?(定义|格式)',
            ]
        },
        'ota': {
            'keywords': [
                'ota', '升级', '固件升级', 'firmware', 'bootloader',
                '开始升级', '升级文件', '文件偏移', '数据块',
                '数据块头', '数据块尾', '升级结束', '升级进度',
                'TYPE', 'STATE', '版本号', '文件长度', 'CRC32',
                '块号', '块数据大小', '数据重传', '退出OTA',
                'CAN OTA', 'RS485 OTA', 'BLE OTA',
                '静默设备', '无备份升级', 'BootLoader模式',
            ],
            'patterns': [
                r'OTA.*?(升级|流程|开始|结束|进度)',
                r'升级.*?(文件|数据块|偏移|CRC)',
                r'0x000[C-F].*?(OTA|升级)',
                r'0x001[0-C].*?(OTA|升级)',
                r'TYPE.*?(0|1|2|3|4|5|6|7)',
                r'STATE.*?(0x00|0x01|0x02|0x03|0x04)',
                r'静默设备.*?(感知|退出)',
                r'无备份.*?(升级|回滚)',
            ]
        },
        'security': {
            'keywords': [
                '安全', '加密', '解密', '密钥', 'AES', 'AES-128', 'ECB',
                'ZeroPadding', '随机数', '挑战应答', '异或加密',
                '会话密钥', '配对随机数', '安全通道', '校验',
                'CRC16', 'CRC32', '完整性校验', '异常检测',
            ],
            'patterns': [
                r'安全.*?(加密|机制|通道)',
                r'加密.*?(AES|异或|随机数)',
                r'配对.*?(随机数|密钥|加密)',
                r'校验.*?(CRC16|CRC32|完整性)',
                r'异或.*?(加密|运算)',
            ]
        },
        'business': {
            'keywords': [
                '业务逻辑', '流程', '场景', '使用场景', '应用场景',
                '配置', '设置', '参数配置', '功能说明', '调试',
                '上位机', '工具使用', '检测', '验证', '适配',
                '配置文件', '解析', 'scale', 'step', 'enum_desc',
            ],
            'patterns': [
                r'业务.*?(逻辑|流程|场景)',
                r'如何.*?(配置|使用|设置|调试)',
                r'怎么.*?(实现|处理|配置|调试)',
                r'上位机.*?(使用|说明|检测)',
                r'配置文件.*?(解析|适配)',
            ]
        },
        'log': {
            'keywords': [
                'log', '日志', '打印', '调试', 'trace', 'debug', 'error',
                '异常', '失败', '超时', '0x[0-9A-Fa-f]+', '错误码',
                '状态码', '故障码', '诊断', '分析', '排查',
            ],
            'patterns': [
                r'log.*?(分析|查看|打印)',
                r'日志.*?(显示|打印|分析)',
                r'0x[0-9A-Fa-f]{2,}.*?(log|日志|错误|故障)',
                r'错误码.*?(含义|解释)',
                r'故障.*?(诊断|排查)',
            ]
        }
    }

    def _rewrite_query(self, question: str) -> Tuple[str, List[str]]:
        """优化查询重写，基于知识库术语标准化"""
        rewritten = question
        hypotheticals = []

        # 应用口语化到技术术语的映射
        for colloquial, tech in COLLOQUIAL_TO_TECH_MAP.items():
            if colloquial in rewritten:
                rewritten = rewritten.replace(colloquial, tech)

        # 处理代词指代
        for pronoun, replacement in PRONOUN_MAP.items():
            if pronoun in rewritten:
                rewritten = rewritten.replace(pronoun, replacement)

        # 基于知识库的特定替换
        # 将模糊的功能码描述具体化
        if '功能码' in rewritten and '0x' not in rewritten:
            if '查询' in rewritten:
                rewritten = rewritten.replace('功能码', '功能码0x0000或0x0003')
            elif '上报' in rewritten:
                rewritten = rewritten.replace('功能码', '功能码0x8001或0x8002')
            elif '下发' in rewritten:
                rewritten = rewritten.replace('功能码', '功能码0x0002')
            elif '配对' in rewritten:
                rewritten = rewritten.replace('功能码', '功能码0x0001')
            elif '升级' in rewritten:
                rewritten = rewritten.replace('功能码', '功能码0x000C-0x001C')

        # 生成假设查询
        for intent_pattern, action_words in INTENT_ACTION_MAP.items():
            if intent_pattern in rewritten:
                for action in action_words:
                    if intent_pattern == '如何':
                        hypothetical = rewritten.replace(intent_pattern, f'如何{action}')
                    else:
                        hypothetical = rewritten.replace(intent_pattern, action)
                    if hypothetical not in hypotheticals:
                        hypotheticals.append(hypothetical)

        # 如果没有生成假设查询，尝试分割长问题
        if not hypotheticals:
            # 尝试按标点分割
            parts = re.split(r'[,，;；]', rewritten)
            if len(parts) > 1:
                for part in parts:
                    part = part.strip()
                    if len(part) > 3 and part not in hypotheticals:
                        hypotheticals.append(part)
            else:
                # 尝试按连接词分割
                parts = re.split(r'[和与及以及或者或]', rewritten)
                if len(parts) > 1:
                    for part in parts:
                        part = part.strip()
                        if len(part) > 3 and part not in hypotheticals:
                            hypotheticals.append(part)

        # 添加基于知识库的常见变体查询
        if '协议' in rewritten.lower():
            base_query = rewritten.lower()
            if 'ble' in base_query or '蓝牙' in base_query:
                hypotheticals.extend(['BLE协议格式', 'BLE功能码定义', 'BLE数据上报'])
            elif 'can' in base_query:
                hypotheticals.extend(['CAN协议格式', 'CAN PGN定义', 'CAN指令下发'])
            elif '485' in base_query or 'rs485' in base_query:
                hypotheticals.extend(['RS485通信格式', 'RS485 DP表', 'RS485功能码'])

        return rewritten, hypotheticals[:5]  # 限制最多5个假设查询

    def classify(self, question: str) -> QuestionIntent:
        """优化分类逻辑，提高知识库关联精度"""
        question_lower = question.lower()
        category_scores: Dict[str, float] = {}
        matched_keywords = []

        rewritten, hypotheticals = self._rewrite_query(question)

        # 第一轮：关键词匹配
        for category, config in self.CATEGORY_PATTERNS.items():
            score = 0.0
            category_keywords = []

            # 关键词匹配（基础分）
            for keyword in config['keywords']:
                keyword_lower = keyword.lower()
                if keyword_lower in question_lower:
                    score += 1.0
                    category_keywords.append(keyword)
                    if keyword not in matched_keywords:
                        matched_keywords.append(keyword)

            # 正则模式匹配（高分）
            for pattern in config['patterns']:
                if re.search(pattern, question, re.IGNORECASE):
                    score += 2.0
                    category_keywords.append(f"pattern:{pattern}")
                    if pattern not in matched_keywords:
                        matched_keywords.append(pattern)

            # 知识库特定内容匹配（额外加分）
            # 检查是否包含知识库特定的功能码、地址等
            hex_matches = self.extract_protocol_fields(question)
            if hex_matches:
                # 根据十六进制值判断可能类别
                for hex_val in hex_matches:
                    if hex_val in ['0x0000', '0x0001', '0x0002', '0x0003', '0x8001', '0x8002']:
                        if category == 'bluetooth':
                            score += 1.5
                    elif hex_val.startswith('0x00FE') or hex_val.startswith('0x00FF'):
                        if category == 'can':
                            score += 1.5
                    elif hex_val in ['0x03', '0x04', '0x83', '0x96']:
                        if category == 'rs485':
                            score += 1.5

            if score > 0:
                category_scores[category] = score

        # 第二轮：如果没有明确匹配，使用默认业务分类
        if not category_scores:
            return QuestionIntent(
                category='business',
                confidence=0.5,
                keywords_matched=[],
                suggested_search=self._build_search_query(question, 'business'),
                rewritten_query=rewritten,
                hypothetical_queries=hypotheticals
            )

        # 选择最佳分类
        best_category = max(category_scores, key=category_scores.get)
        max_score = category_scores[best_category]
        
        # 计算置信度（基于匹配分数和匹配数量）
        base_confidence = min(max_score / 5.0, 1.0)  # 调整分母为5.0以适应更高分数
        
        # 如果有多个关键词匹配，提高置信度
        keyword_count = len([k for k in matched_keywords if not k.startswith('pattern:')])
        if keyword_count > 1:
            base_confidence = min(base_confidence + 0.1 * (keyword_count - 1), 1.0)
            
        confidence = base_confidence

        return QuestionIntent(
            category=best_category,
            confidence=confidence,
            keywords_matched=matched_keywords,
            suggested_search=self._build_search_query(question, best_category),
            rewritten_query=rewritten,
            hypothetical_queries=hypotheticals
        )

    def _build_search_query(self, question: str, category: str) -> str:
        """构建针对知识库的优化搜索查询"""
        # 基础查询
        base_query = question
        
        # 根据分类添加特定搜索词
        category_enhancements = {
            'bluetooth': ['云迹物联 BLE协议', '蓝牙基础协议', '功能码', 'DP上报'],
            'can': ['E-bike Smart CAN协议', 'CAN通讯协议', 'PGN', '帧ID'],
            'rs485': ['RS485通信协议', '主从通信', 'DP表', '功能码'],
            'dp': ['数据点定义', 'DP格式', 'dp_id', 'dp_type'],
            'ota': ['OTA升级流程', '固件升级', '升级协议', '数据块'],
            'security': ['安全加密', '配对绑定', 'AES加密', '异或加密'],
            'business': ['业务逻辑', '使用场景', '配置说明', '调试方法'],
            'log': ['日志分析', '错误码', '故障诊断', '调试日志'],
        }
        
        enhancement = category_enhancements.get(category, [])
        
        # 提取关键实体
        entities = []
        
        # 提取十六进制值（功能码、地址等）
        hex_values = self.extract_protocol_fields(question)
        if hex_values:
            entities.extend(hex_values)
            
        # 提取DP ID
        dp_ids = self.extract_dp_ids(question)
        if dp_ids:
            entities.extend([f'dp{id}' for id in dp_ids])
            
        # 构建最终搜索查询
        search_parts = []
        
        # 1. 原始问题（精简版）
        if len(base_query) > 20:
            # 取前20个字符作为核心描述
            core_desc = base_query[:20] + '...'
            search_parts.append(core_desc)
        else:
            search_parts.append(base_query)
            
        # 2. 分类增强词
        if enhancement:
            search_parts.extend(enhancement[:2])  # 最多加2个增强词
            
        # 3. 关键实体
        if entities:
            search_parts.extend(entities[:3])  # 最多加3个实体
            
        # 组合搜索查询
        search_query = ' '.join(search_parts)
        
        # 如果查询太长，进行精简
        if len(search_query) > 50:
            # 优先保留实体和增强词
            important_parts = []
            if entities:
                important_parts.extend(entities[:2])
            if enhancement:
                important_parts.extend(enhancement[:1])
                
            if important_parts:
                search_query = ' '.join(important_parts)
            else:
                search_query = base_query[:50]
                
        return search_query.strip()

    def extract_protocol_fields(self, question: str) -> List[str]:
        """提取协议相关字段：功能码、地址、PGN等"""
        hex_pattern = r'0x([0-9A-Fa-f]{2,8})'
        matches = re.findall(hex_pattern, question)
        
        hex_values = [f'0x{m}' for m in matches]
        
        # 根据知识库常见格式进一步筛选
        filtered_values = []
        for val in hex_values:
            # BLE功能码：0x0000-0x0025, 0x8001-0x8005
            if re.match(r'0x000[0-9A-Fa-f]|0x001[0-9A-Fa-f]|0x002[0-5]|0x800[1-5]', val):
                filtered_values.append(val)
            # CAN PGN：0x00xxxx
            elif re.match(r'0x00[0-9A-Fa-f]{4}', val):
                filtered_values.append(val)
            # RS485地址和功能码：0x01-0x04, 0x03, 0x04, 0x83, 0x96
            elif val in ['0x01', '0x02', '0x03', '0x04', '0x83', '0x96']:
                filtered_values.append(val)
            # 其他有意义的十六进制值（长度>=4）
            elif len(val) >= 6:  # 0x + 至少4位十六进制
                filtered_values.append(val)
                
        return filtered_values

    def extract_dp_ids(self, question: str) -> List[str]:
        """提取DP ID，支持多种格式"""
        dp_patterns = [
            r'dp[_\s]*(\d+)',           # dp_123, dp 123
            r'数据点[_\s]*(\d+)',        # 数据点123
            r'dp_id[_\s]*(\d+)',         # dp_id 123
            r'功能点[_\s]*(\d+)',        # 功能点123
            r'DP[_\s]*(\d+)',           # DP123
        ]
        
        dp_ids = []
        for pattern in dp_patterns:
            matches = re.findall(pattern, question, re.IGNORECASE)
            dp_ids.extend(matches)
            
        # 去重并返回
        return list(set(dp_ids))
