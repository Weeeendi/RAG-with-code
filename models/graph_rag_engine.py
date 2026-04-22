import json
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict
import sys
sys.path.insert(0, r'D:\workspace\Agent')

from models.code_distiller import CodeDistiller, KnowledgeGraphStore, DistilledKnowledge
from models.code_analysis import CallGraphExtractor, RelationshipMapper, LogicSkeletonExtractor


class GraphRAGEngine:
    def __init__(self, source_dir: str = None):
        self.source_dir = source_dir
        self.code_distiller = CodeDistiller()
        self.graph_store = KnowledgeGraphStore()
        self.call_graph_extractor = None
        self.relationship_mapper = None
        self.logic_extractor = None

        if source_dir:
            self.call_graph_extractor = CallGraphExtractor(source_dir)
            self.relationship_mapper = RelationshipMapper(source_dir)
            self.logic_extractor = LogicSkeletonExtractor(source_dir)

    def index_codebase(self, source_dir: str = None) -> Dict[str, Any]:
        if source_dir:
            self.source_dir = source_dir

        if not self.source_dir:
            return {"status": "error", "message": "No source directory provided"}

        stats = {
            "functions_indexed": 0,
            "state_machines_indexed": 0,
            "structs_indexed": 0,
            "enums_indexed": 0,
            "edges_created": 0,
            "errors": []
        }

        print("[GraphRAG] Extracting call graph...")
        call_graph = self.call_graph_extractor.extract_from_directory()
        call_graph_data = self.call_graph_extractor.export_to_dict()

        print("[GraphRAG] Extracting relationships...")
        rel_graph = self.relationship_mapper.extract_from_directory()
        rel_graph_data = self.relationship_mapper.export_to_dict()

        print("[GraphRAG] Extracting logic skeletons...")
        logic_data = self.logic_extractor.extract_from_directory()

        print("[GraphRAG] Distilling knowledge...")

        for node_data in call_graph_data.get('nodes', []):
            if node_data['type'] == 'function' and node_data.get('calls'):
                try:
                    node_id = f"func_{node_data['name']}"

                    distilled = self.code_distiller.distill_code_block(
                        code=node_data.get('content', ''),
                        code_type='function',
                        name=node_data['name']
                    )

                    module_name = self._get_module_name(node_data.get('file', ''))
                    self.graph_store.add_node(
                        node=distilled,
                        module_name=module_name,
                        file_path=node_data.get('file', ''),
                        line_number=node_data.get('line', 0)
                    )
                    stats["functions_indexed"] += 1

                    for called_func in node_data.get('calls', []):
                        self.graph_store.add_edge(
                            from_node=node_id,
                            to_node=f"func_{called_func}",
                            edge_type='calls',
                            description=f"{node_data['name']} calls {called_func}"
                        )
                        stats["edges_created"] += 1

                except Exception as e:
                    stats["errors"].append(f"Function {node_data.get('name')}: {str(e)}")

        for sm_data in logic_data.get('state_machines', []):
            try:
                distilled = self.code_distiller.distill_state_machine(
                    state_machine_code=sm_data.get('description', ''),
                    sm_name=sm_data.get('name', '')
                )

                sm_node = DistilledKnowledge(
                    node_id=f"sm_{sm_data['name']}",
                    node_type='state_machine',
                    original_code=json.dumps(sm_data, ensure_ascii=False),
                    distilled_content=json.dumps(distilled, ensure_ascii=False),
                    business_description=distilled.get('purpose', sm_data.get('description', '')),
                    keywords=['状态机', '状态转移'] + distilled.get('states', []),
                    metadata={'states': distilled.get('states', []), 'transitions': len(distilled.get('transitions', []))}
                )

                self.graph_store.add_node(
                    node=sm_node,
                    module_name=self._get_module_name(sm_data.get('file', '')),
                    file_path=sm_data.get('file', ''),
                    line_number=sm_data.get('line', 0)
                )
                stats["state_machines_indexed"] += 1

            except Exception as e:
                stats["errors"].append(f"State machine {sm_data.get('name')}: {str(e)}")

        print(f"[GraphRAG] Indexing complete: {stats['functions_indexed']} functions, {stats['state_machines_indexed']} state machines")

        return stats

    def _get_module_name(self, file_path: str) -> str:
        if not file_path:
            return 'unknown'
        parts = file_path.replace('\\', '/').split('/')
        for part in reversed(parts):
            if part not in ['Src', 'Inc', 'components', 'modules', 'VL', 'driver', 'utils', 'common']:
                return part.replace('.c', '').replace('.h', '')
        return 'unknown'

    def retrieve_with_graph(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        keywords = self._extract_keywords(query)

        direct_results = []
        for kw in keywords:
            results = self.graph_store.search_by_keyword(kw, limit=top_k)
            direct_results.extend(results)

        unique_results = {r['node_id']: r for r in direct_results}.values()

        graph_expanded_results = []
        for result in list(unique_results)[:top_k]:
            node_id = result['node_id']
            related = self.graph_store.get_related_nodes(node_id, edge_type='calls', depth=2)
            graph_expanded_results.extend(related)

        all_results = list(unique_results) + graph_expanded_results
        unique_all = {r['node_id']: r for r in all_results}.values()

        scored_results = []
        for r in unique_all:
            score = 0.0
            query_lower = query.lower()
            r_keywords = [kw.lower() for kw in r.get('keywords', [])]
            r_desc = r.get('business_description', '').lower()

            for kw in keywords:
                if kw.lower() in r_keywords:
                    score += 3.0
                if kw.lower() in r_desc:
                    score += 1.0

            if 'DP' in query.upper() and 'dp' in r.get('node_id', '').lower():
                score += 2.0

            scored_results.append((r, score))

        scored_results.sort(key=lambda x: x[1], reverse=True)

        return [r for r, score in scored_results[:top_k]]

    def _extract_keywords(self, query: str) -> List[str]:
        keywords = []

        tech_terms = {
            'BLE': ['ble', 'bluetooth', '蓝牙', '配对'],
            'HID': ['hid', '人机接口'],
            'OTA': ['ota', '升级', 'update', '固件'],
            'DP': ['dp', '数据点', 'datapoint', '上报'],
            'RS485': ['rs485', 'can', '总线', 'uart'],
            'MQTT': ['mqtt', 'topic', '发布', '订阅'],
            'Battery': ['battery', '电量', '电池', 'bms'],
            'Riding': ['riding', '骑行', '里程', 'mileage'],
            'Fault': ['fault', '故障', 'alarm', '报警'],
            'Record': ['record', '记录', 'history', 'log'],
        }

        query_lower = query.lower()
        for tech, terms in tech_terms.items():
            if any(term in query_lower for term in terms):
                keywords.append(tech)
                keywords.extend(terms)

        number_match = re.search(r'DP\s*(\d+)', query, re.IGNORECASE)
        if number_match:
            keywords.append(f"DP{number_match.group(1)}")

        cmd_match = re.search(r'0x([0-9A-Fa-f]+)', query)
        if cmd_match:
            keywords.append(f"0x{cmd_match.group(1).upper()}")

        return list(set(keywords))[:10]

    def get_logic_chain_for_dp(self, dp_name: str) -> str:
        results = self.graph_store.search_by_keyword(dp_name, limit=5)

        if not results:
            return f"未找到与 {dp_name} 相关的逻辑链"

        chain_parts = []
        for r in results[:3]:
            node_id = r.get('node_id', '')
            chain_desc = self.graph_store.get_call_chain_description(node_id, max_depth=3)
            if chain_desc and chain_desc != "调用链描述不可用":
                chain_parts.append(f"[{r.get('name', node_id)}]: {chain_desc}")

        if chain_parts:
            return " | ".join(chain_parts)
        return f"找到 {len(results)} 个相关节点，但无法构建完整逻辑链"

    def build_answer_context(self, query: str, retrieved_nodes: List[Dict]) -> str:
        if not retrieved_nodes:
            return "知识库中未找到相关信息"

        context_parts = []

        for node in retrieved_nodes:
            node_type = node.get('node_type', 'unknown')
            name = node.get('name', node.get('node_id', ''))
            business_desc = node.get('business_description', '')

            if node_type == 'function':
                context_parts.append(f"【函数逻辑】{name}\n{business_desc}")

                related = self.graph_store.get_related_nodes(node.get('node_id'), edge_type='calls', depth=1)
                if related:
                    related_descs = [f"{n['name']}({n.get('edge_type', '')})" for n in related[:3]]
                    context_parts.append(f"  → 调用关系: {', '.join(related_descs)}")

            elif node_type == 'state_machine':
                context_parts.append(f"【状态机】{name}\n{business_desc}")
                metadata = node.get('metadata', {})
                if 'states' in metadata:
                    context_parts.append(f"  → 状态列表: {', '.join(metadata['states'][:5])}")

            elif node_type == 'struct':
                context_parts.append(f"【数据结构】{name}\n{business_desc}")

            else:
                context_parts.append(f"【{node_type}】{name}\n{business_desc}")

        return "\n---\n".join(context_parts)


class BlackBoxProcessor:
    SANITIZE_RULES = {
        'replace_variables': [
            (r'\b[a-z][a-z0-9_]{0,30}\b', '<var>'),
        ],
        'replace_arrays': [
            (r'\[\d+\]', '[<size>]'),
        ],
        'replace_hex_values': [
            (r'0x[0-9A-Fa-f]+', '<hex>'),
        ],
        'replace_numbers': [
            (r'\b\d+\b', '<num>'),
        ],
    }

    @classmethod
    def sanitize_code_reference(cls, code_snippet: str) -> str:
        sanitized = code_snippet

        sanitized = re.sub(r'//.*$', '', sanitized, flags=re.MULTILINE)
        sanitized = re.sub(r'/\*.*?\*/', '', sanitized, flags=re.DOTALL)

        sanitized = re.sub(r'\s+', ' ', sanitized)

        return sanitized.strip()

    @classmethod
    def extract_structural_elements(cls, code: str) -> Dict[str, Any]:
        elements = {
            'has_loop': bool(re.search(r'\b(for|while|do)\b', code)),
            'has_condition': bool(re.search(r'\b(if|switch|case)\b', code)),
            'has_return': bool(re.search(r'\breturn\b', code)),
            'has_pointer': '*' in code,
            'has_array': bool(re.search(r'\[', code)),
            'complexity_estimate': 0
        }

        if elements['has_loop']:
            elements['complexity_estimate'] += 1
        if elements['has_condition']:
            elements['complexity_estimate'] += 1
        if elements['has_pointer']:
            elements['complexity_estimate'] += 1

        if_code = re.findall(r'if\s*\(', code)
        elements['complexity_estimate'] += len(if_code)

        return elements

    @classmethod
    def should_expose_code(cls, context: str) -> bool:
        safe_keywords = [
            '示例', 'example', '示意', 'pseudocode', '伪代码',
            '结构', 'structure', 'format', '格式', '协议', 'protocol'
        ]
        return any(kw in context.lower() for kw in safe_keywords)