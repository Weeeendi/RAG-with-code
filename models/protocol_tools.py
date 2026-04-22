import json
import os
import re
from typing import Dict, Any, Optional, List

TOOLS_DIR = os.path.join(os.path.dirname(__file__), '..', 'knowledge_base', 'raw', 'tools')

DP_DATA_PATH = os.path.join(TOOLS_DIR, 'dp_protocal', 'dp-data.js')
RS485_DICT_PATH = os.path.join(TOOLS_DIR, 'rs485_protocal', 'rs485_dp_dict.js')


class DPTools:
    def __init__(self):
        self.dp_data = self._load_dp_data()
        self.rs485_dict = self._load_rs485_dict()

    def _load_dp_data(self) -> Dict[str, Any]:
        if not os.path.exists(DP_DATA_PATH):
            return {}
        try:
            with open(DP_DATA_PATH, 'r', encoding='utf-8') as f:
                content = f.read()
            match = re.search(r'const\s+dpData\s*=\s*\{(.*?)\}\s*;', content, re.DOTALL)
            if match:
                dp_text = '{' + match.group(1) + '}'
                dp_text = re.sub(r',(\s*[\]}])', r'\1', dp_text)
                return json.loads(dp_text)
        except Exception as e:
            print(f"Error loading dp-data.js: {e}")
        return {}

    def _load_rs485_dict(self) -> Dict[int, Any]:
        if not os.path.exists(RS485_DICT_PATH):
            return {}
        try:
            with open(RS485_DICT_PATH, 'r', encoding='utf-8') as f:
                content = f.read()

            result = {}
            entry_pattern = re.compile(r'(\d+)\s*:\s*\{([^}]+)\}')
            field_pattern = re.compile(r'(\w+)\s*:\s*("[^"]*"|\S+?)(\s*(?:,|}))')

            for match in entry_pattern.finditer(content):
                dpid = int(match.group(1))
                fields_str = match.group(2)
                entry = {}

                for field_match in field_pattern.finditer(fields_str):
                    key = field_match.group(1)
                    value = field_match.group(2).strip()

                    if key == 'id':
                        pass
                    elif key == 'type':
                        try:
                            if value.startswith('0x'):
                                value = int(value, 16)
                            else:
                                value = int(value)
                        except:
                            pass
                    elif value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]

                    entry[key] = value

                result[dpid] = entry

            return result
        except Exception as e:
            print(f"Error loading rs485_dp_dict.js: {e}")
            import traceback
            traceback.print_exc()
        return {}

    def lookup_dp_id(self, dp_id: str) -> Optional[Dict[str, Any]]:
        dp_id_str = str(dp_id).strip()
        if dp_id_str in self.dp_data:
            return self.dp_data[dp_id_str]
        return None

    def lookup_rs485_dp(self, dp_id: int) -> Optional[Dict[str, Any]]:
        try:
            dp_key = int(dp_id)
            if dp_key in self.rs485_dict:
                return self.rs485_dict[dp_key]
        except ValueError:
            pass
        return None

    def search_dp_by_name(self, keyword: str) -> List[Dict[str, Any]]:
        results = []
        keyword_lower = keyword.lower()
        for dp_id, info in self.dp_data.items():
            if keyword_lower in info.get('dp_name', '').lower() or keyword_lower in info.get('dp_code', '').lower():
                results.append({'dp_id': dp_id, **info})
        return results[:10]

    def search_rs485_by_name(self, keyword: str) -> List[Dict[str, Any]]:
        results = []
        keyword_lower = keyword.lower()
        for dp_id, info in self.rs485_dict.items():
            if keyword_lower in info.get('name', '').lower():
                results.append({'dp_id': dp_id, **info})
        return results[:10]

    def parse_dp_hex_data(self, hex_str: str) -> Dict[str, Any]:
        result = {'raw': hex_str, 'parsed': {}}
        try:
            clean_hex = hex_str.replace(' ', '').replace('0x', '')
            if len(clean_hex) >= 2:
                result['byte_count'] = len(clean_hex) // 2
                result['parsed']['byte_values'] = [int(clean_hex[i:i+2], 16) for i in range(0, len(clean_hex), 2)]
        except Exception:
            pass
        return result


_dp_tools_instance = None


def get_dp_tools() -> DPTools:
    global _dp_tools_instance
    if _dp_tools_instance is None:
        _dp_tools_instance = DPTools()
    return _dp_tools_instance


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_dp_id",
            "description": "根据DP ID查找BLE协议中数据点的定义信息，包括名称、数据类型等。适用于查询特定DP ID的含义，如查询DP 1表示什么功能。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dp_id": {
                        "type": "string",
                        "description": "DP ID编号，如 '1', '2', '16', '21' 等"
                    }
                },
                "required": ["dp_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_rs485_dp",
            "description": "根据DP ID查找RS485协议中数据点的定义信息。RS485协议的DP ID通常为5位数，如10001(开关机)、20001(仪表开关机)、40001(IoT开关机)等。",
            "parameters": {
                "type": "object",
                "properties": {
                    "dp_id": {
                        "type": "integer",
                        "description": "RS485 DP ID，如 10001, 20001, 40001 等"
                    }
                },
                "required": ["dp_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_dp_by_name",
            "description": "在BLE协议的DP数据点中搜索包含关键词的数据点。适用于不知道具体DP ID时，根据功能名称搜索对应的DP。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如 '速度', '电量', '故障', '里程' 等"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_rs485_by_name",
            "description": "在RS485协议的DP数据点中搜索包含关键词的数据点。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如 '电池', '档位', '故障' 等"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_code",
            "description": "检索代码库中函数实现，用于查找嵌入式代码中特定功能的实现逻辑。当发现DP ID或需要了解代码实现时必须调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如 'riding_end', 'dp_report', 'mcu_dp' 等"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "parse_hex_data",
            "description": "解析十六进制数据字符串，将其转换为字节数组。适用于解析设备上报的原始十六进制数据。",
            "parameters": {
                "type": "object",
                "properties": {
                    "hex_str": {
                        "type": "string",
                        "description": "十六进制字符串，如 '01 02 03 04' 或 '01020304' 或 '0x010x020x030x04'"
                    }
                },
                "required": ["hex_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "通用知识检索工具，在整个知识库中搜索协议文档、代码注释等。当精确DP搜索失败或需要了解业务流程时必须调用此工具。",
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如 '骑行记录', 'App上报', '8005', '行程触发条件' 等"
                    }
                },
                "required": ["keyword"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "paddleocr_mcp",
            "description": "使用PaddleOCR解析PDF文档，提取文本和表格内容。适用于扫描版PDF、截图、表格图片等无法直接提取文本的文档。调用后结果自动合并到知识库。",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "PDF文件的绝对路径，如 'D:/workspace/Agent/knowledge_base/raw/protocol_docs/App内dp上报逻辑.pdf'"
                    }
                },
                "required": ["file_path"]
            }
        }
    }
]


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    tools = get_dp_tools()

    if tool_name == "lookup_dp_id":
        result = tools.lookup_dp_id(arguments.get("dp_id", ""))
        if result:
            return {"success": True, "data": result}
        return {"success": False, "error": f"DP ID '{arguments.get('dp_id')}' not found in BLE protocol"}

    elif tool_name == "lookup_rs485_dp":
        result = tools.lookup_rs485_dp(arguments.get("dp_id", 0))
        if result:
            return {"success": True, "data": result}
        return {"success": False, "error": f"DP ID '{arguments.get('dp_id')}' not found in RS485 protocol"}

    elif tool_name == "search_dp_by_name":
        results = tools.search_dp_by_name(arguments.get("keyword", ""))
        if results:
            return {"success": True, "data": results, "count": len(results)}
        return {"success": False, "error": f"No BLE DP found matching '{arguments.get('keyword')}'"}

    elif tool_name == "search_rs485_by_name":
        results = tools.search_rs485_by_name(arguments.get("keyword", ""))
        if results:
            return {"success": True, "data": results, "count": len(results)}
        return {"success": False, "error": f"No RS485 DP found matching '{arguments.get('keyword')}'"}

    elif tool_name == "search_code":
        from models.vector_store import KnowledgeBase
        kb = KnowledgeBase()
        keyword = arguments.get("keyword", "")
        results = kb.search(keyword, category='c_code', top_k=5)
        if results:
            data = [{'id': r.id, 'title': r.title, 'content': r.content[:500]} for r in results]
            return {"success": True, "data": data, "count": len(data)}
        return {"success": False, "error": f"No code found matching '{keyword}'"}

    elif tool_name == "parse_hex_data":
        result = tools.parse_dp_hex_data(arguments.get("hex_str", ""))
        return {"success": True, "data": result}

    elif tool_name == "search_knowledge":
        from models.vector_store import KnowledgeBase
        from config import DB_PATH, VECTOR_DIR
        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)
        keyword = arguments.get("keyword", "")
        results = kb.search(keyword, category='protocol', top_k=5)
        if not results:
            results = kb.search(keyword, top_k=5)
        if results:
            data = [{'id': r.id, 'type': r.type, 'title': r.title, 'content': r.content[:500]} for r in results]
            return {"success": True, "data": data, "count": len(data)}
        return {"success": False, "error": f"No knowledge found matching '{keyword}'"}

    elif tool_name == "paddleocr_mcp":
        from models.paddleocr_parser import parse_with_paddleocr
        file_path = arguments.get("file_path", "")
        if not file_path:
            return {"success": False, "error": "file_path is required"}
        try:
            blocks = parse_with_paddleocr(file_path)
            if blocks:
                return {"success": True, "data": {
                    "blocks": len(blocks),
                    "title": blocks[0].get("title", "Untitled"),
                    "content_length": len(blocks[0].get("content", "")),
                    "message": f"Parsed {len(blocks)} blocks from PDF"
                }}
            return {"success": False, "error": "No content extracted from PDF"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    return {"success": False, "error": f"Unknown tool: {tool_name}"}