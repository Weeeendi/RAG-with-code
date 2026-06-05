"""
Code Graph Extractor using Tree-sitter
基于Tree-sitter的C代码函数调用图/关系图提取器
"""
import os
import re
import json
import hashlib
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field, asdict

from tree_sitter import Parser, Tree
from tree_sitter_languages import get_language


@dataclass
class GraphNode:
    id: str
    type: str  # function, variable, struct, enum, typedef
    name: str
    code_snippet: str = ""
    file: str = ""
    line_start: int = 0
    line_end: int = 0
    subsystem: str = ""
    context: str = ""
    metadata: Dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    from_node: str
    to_node: str
    edge_type: str  # calls, accesses, includes, defines
    metadata: Dict = field(default_factory=dict)


class TreeSitterExtractor:
    """基于Tree-sitter的C代码提取器"""

    def __init__(self, lang):
        self.lang = lang
        self.parser = Parser()
        self.parser.set_language(lang)

    def parse(self, code: bytes) -> Tree:
        return self.parser.parse(code)

    def get_node_text(self, node) -> str:
        """获取节点对应的源代码文本"""
        return node.text.decode('utf-8', errors='replace') if node.text else ""

    def extract_functions(self, tree: Tree, file_name: str, subsystem: str, context: str) -> Tuple[List[GraphNode], Set[str]]:
        """提取函数定义"""
        nodes = []
        func_names = set()

        # 直接遍历AST查找function_definition
        for node in self._find_nodes(tree.root_node, 'function_definition'):
            func_name = self._get_function_name(node)
            if not func_name:
                continue

            func_names.add(func_name)
            code_snippet = self.get_node_text(node)[:800]
            line_start = node.start_point[0] + 1
            line_end = node.end_point[0] + 1

            node_id = f"func:{func_name}"
            params = self._get_function_params(node)

            graph_node = GraphNode(
                id=node_id,
                type="function",
                name=func_name,
                code_snippet=code_snippet,
                file=file_name,
                line_start=line_start,
                line_end=line_end,
                subsystem=subsystem,
                context=context,
                metadata={"params": params}
            )
            nodes.append(graph_node)

        return nodes, func_names

    def _find_nodes(self, node, node_type: str) -> List:
        """递归查找所有指定类型的节点"""
        result = []
        if node.type == node_type:
            result.append(node)
        for child in node.children:
            result.extend(self._find_nodes(child, node_type))
        return result

    def _get_function_name(self, node) -> Optional[str]:
        """从function_definition节点获取函数名"""
        # function_definition 结构: type declarator compound_statement
        # declarator 结构: identifier parameter_list 或 (pointer)? identifier (parameter_list)?
        declarator = node.child_by_field_name('declarator')
        if not declarator:
            return None

        # 尝试获取identifier
        identifier = declarator.child_by_field_name('declarator') or declarator.child_by_field_name('name')
        if identifier and identifier.type == 'identifier':
            return self.get_node_text(identifier)

        # 递归查找identifier
        for child in declarator.children:
            if child.type == 'identifier':
                return self.get_node_text(child)

        return None

    def _get_function_params(self, node) -> str:
        """从function_definition节点获取参数列表"""
        declarator = node.child_by_field_name('declarator')
        if not declarator:
            return ""

        param_list = declarator.child_by_field_name('parameters')
        if param_list and param_list.type == 'parameter_list':
            params = []
            for child in param_list.children:
                if child.type == 'parameter_declaration':
                    # 获取参数类型和名称
                    type_parts = []
                    name_part = None
                    for c in child.children:
                        if c.type == 'type_identifier' or c.type == 'primitive_type':
                            type_parts.append(self.get_node_text(c))
                        elif c.type == 'identifier':
                            name_part = self.get_node_text(c)
                        elif c.type == 'pointer_declarator':
                            # 指针参数
                            for pc in c.children:
                                if pc.type == 'identifier':
                                    name_part = self.get_node_text(pc)
                                    break
                    if name_part:
                        params.append(name_part)
                    else:
                        params.append(' '.join(type_parts) if type_parts else '...')
            return ', '.join(params)

        return ""

    def extract_types(self, tree: Tree, file_name: str, subsystem: str, context: str) -> List[GraphNode]:
        """提取类型定义（struct, enum, typedef）"""
        nodes = []

        # struct
        for node in self._query_nodes(tree, 'type_definition'):
            decl = node.child_by_field_name('declaration')
            if decl and decl.type == 'struct_specifier':
                name_node = decl.child_by_field_name('name')
                if name_node:
                    name = self.get_node_text(name_node)
                    if name:
                        node_id = f"struct:{name}"
                        fields = self._get_struct_fields(decl)
                        nodes.append(GraphNode(
                            id=node_id,
                            type="struct",
                            name=name,
                            code_snippet=self.get_node_text(node)[:400],
                            file=file_name,
                            line_start=node.start_point[0] + 1,
                            line_end=node.end_point[0] + 1,
                            subsystem=subsystem,
                            context=context,
                            metadata={"fields": fields}
                        ))

        # enum
        for node in self._query_nodes(tree, 'enum_specifier'):
            name_node = node.child_by_field_name('name')
            name = self.get_node_text(name_node) if name_node else None
            if name:
                node_id = f"enum:{name}"
                values = self._get_enum_values(node)
                nodes.append(GraphNode(
                    id=node_id,
                    type="enum",
                    name=name,
                    code_snippet=self.get_node_text(node)[:400],
                    file=file_name,
                    line_start=node.start_point[0] + 1,
                    line_end=node.end_point[0] + 1,
                    subsystem=subsystem,
                    context=context,
                    metadata={"values": values}
                ))

        return nodes

    def _get_struct_fields(self, node) -> List[str]:
        """获取struct字段列表"""
        fields = []
        field_list = node.child_by_field_name('body')
        if field_list and field_list.type == 'declaration_list':
            for child in field_list.children:
                if child.type == 'field_declaration':
                    # 字段声明通常是 identifier: type 的形式
                    for c in child.children:
                        if c.type == 'field_identifier':
                            fields.append(self.get_node_text(c))
        return fields

    def _get_enum_values(self, node) -> List[str]:
        """获取enum值列表"""
        values = []
        body = node.child_by_field_name('body')
        if body and body.type == 'enumerator_list':
            for child in body.children:
                if child.type == 'enumerator':
                    name_node = child.child_by_field_name('name')
                    if name_node:
                        values.append(self.get_node_text(name_node))
        return values

    def extract_variables(self, tree: Tree, file_name: str, subsystem: str, context: str, exclude_funcs: Set[str]) -> List[GraphNode]:
        """提取全局变量"""
        nodes = []

        # 查找translation_unit级别的声明语句
        root = tree.root_node
        for child in root.children:
            if child.type == 'declaration':
                # 检查是否在函数外部（通过位置判断简单排除）
                decl_text = self.get_node_text(child)
                # 跳过函数声明 extern
                if 'extern' in decl_text:
                    continue
                # 跳过包含函数调用的声明
                if '(' in decl_text and ')' in decl_text and not decl_text.strip().startswith('#'):
                    continue
                # 查找identifier
                for c in child.children:
                    if c.type == 'identifier':
                        name = self.get_node_text(c)
                        if name and name not in exclude_funcs and not name.startswith('_'):
                            nodes.append(GraphNode(
                                id=f"var:{name}",
                                type="variable",
                                name=name,
                                code_snippet=decl_text[:200],
                                file=file_name,
                                line_start=child.start_point[0] + 1,
                                line_end=child.end_point[0] + 1,
                                subsystem=subsystem,
                                context=context,
                                metadata={"decl": "global"}
                            ))
                        break

        return nodes

    def extract_calls(self, tree: Tree, func_names: Set[str], builtin_funcs: Set[str]) -> List[GraphEdge]:
        """提取函数调用关系"""
        edges = []

        # 使用Query查找所有函数定义中的调用
        all_funcs = func_names | builtin_funcs

        # 遍历所有函数定义
        for func_node in self._query_nodes(tree, 'function_definition'):
            caller_name = self._get_function_name(func_node)
            if not caller_name:
                continue

            caller_id = f"func:{caller_name}"

            # 在函数体中查找call_expression
            body = func_node.child_by_field_name('body')
            if body:
                calls = self._find_calls(body, caller_id, all_funcs)
                edges.extend(calls)

        return edges

    def _find_calls(self, node, caller_id: str, known_funcs: Set[str]) -> List[GraphEdge]:
        """递归查找函数调用"""
        edges = []

        if node.type == 'call_expression':
            # 获取被调用的函数名
            func_name_node = node.child_by_field_name('function')
            if func_name_node:
                if func_name_node.type == 'identifier':
                    callee_name = self.get_node_text(func_name_node)
                else:
                    # 可能是表达式如 pointer->member
                    callee_name = None
                    for c in func_name_node.children:
                        if c.type == 'identifier':
                            callee_name = self.get_node_text(c)
                            break

                if callee_name:
                    callee_id = f"func:{callee_name}" if callee_name in known_funcs else f"ext:{callee_name}"
                    edges.append(GraphEdge(
                        from_node=caller_id,
                        to_node=callee_id,
                        edge_type="calls",
                        metadata={"callee": callee_name}
                    ))

        # 递归遍历子节点
        for child in node.children:
            edges.extend(self._find_calls(child, caller_id, known_funcs))

        return edges

    def _query_nodes(self, tree: Tree, node_type: str) -> List:
        """查找所有指定类型的节点"""
        result = []

        def walk(node):
            if node.type == node_type:
                result.append(node)
            for child in node.children:
                walk(child)

        walk(tree.root_node)
        return result


class CodeGraphExtractor:
    """C代码图关系提取器主类"""

    # 内置函数列表
    BUILTIN_FUNCS = {
        'printf', 'scanf', 'malloc', 'free', 'memcpy', 'memset', 'strlen',
        'strcpy', 'strncpy', 'strcmp', 'memcmp', 'memmove', 'sprintf',
        'snprintf', 'atoi', 'atof', 'strtol', 'strdup', 'calloc',
        'realloc', 'exit', 'abort', 'assert', 'sizeof', 'offsetof',
        'vsprintf', 'vprintf', 'sscanf', 'strcat', 'strncat', 'memchr',
        'localtime', 'gmtime', 'time', 'srand', 'rand', 'xQueueSendToBack',
        'xTaskGetTickCount', 'VL_LOG_DEBUG', 'VL_LOG_ERROR', 'VL_LOG_HEXDUMP_DEBUG'
    }

    def __init__(self, source_dir: str = "knowledge_base/raw/c_code"):
        self.source_dir = source_dir
        self.parsed_files: Dict[str, float] = {}
        self.graphs: Dict[str, dict] = {}

        # 初始化tree-sitter
        self.lang = get_language('c')
        self.extractor = TreeSitterExtractor(self.lang)

    def extract_from_file(self, file_path: str) -> dict:
        """从C文件提取图结构"""
        from models.utils.text_cleaner import sanitize_text

        with open(file_path, 'rb') as f:
            raw = f.read()

        # 尝试编码检测
        try:
            from charset_normalizer import from_bytes
            results = from_bytes(raw, steps=10)
            best = results.best()
            content = str(best) if best else raw.decode('utf-8', errors='replace')
        except ImportError:
            content = raw.decode('utf-8', errors='replace')

        content = sanitize_text(content)
        code_bytes = content.encode('utf-8')

        file_name = os.path.basename(file_path)
        subsystem, context = self._detect_subsystem(file_path)

        try:
            tree = self.extractor.parse(code_bytes)
        except Exception as e:
            import sys
            print(f"Tree-sitter解析失败 {file_name}: {e}", file=sys.stderr)
            return {
                "nodes": [],
                "edges": [],
                "file": file_name,
                "full_path": file_path,
                "total_lines": len(content.split('\n')),
                "subsystem": subsystem,
                "context": context
            }

        # 提取函数
        func_nodes, func_names = self.extractor.extract_functions(tree, file_name, subsystem, context)

        # 提取类型
        type_nodes = self.extractor.extract_types(tree, file_name, subsystem, context)

        # 提取全局变量
        var_nodes = self.extractor.extract_variables(tree, file_name, subsystem, context, func_names)

        # 提取调用关系
        all_funcs = func_names | self.BUILTIN_FUNCS
        call_edges = self.extractor.extract_calls(tree, func_names, self.BUILTIN_FUNCS)

        all_nodes = func_nodes + type_nodes + var_nodes

        return {
            "nodes": [asdict(n) for n in all_nodes],
            "edges": [asdict(e) for e in call_edges],
            "file": file_name,
            "full_path": file_path,
            "total_lines": len(content.split('\n')),
            "subsystem": subsystem,
            "context": context
        }

    def _detect_subsystem(self, file_path: str) -> tuple:
        """根据文件路径检测代码所属子系统和上下文"""
        path_lower = file_path.replace('\\', '/').lower()

        subsystem_map = {
            'gil': ('gil/gps', 'GPS定位/GNSS卫星定位状态'),
            'gnss': ('gil/gps', 'GPS定位/GNSS卫星定位状态'),
            'cil': ('cil/ble', 'BLE蓝牙通信/CIL适配器'),
            'btdm': ('cil/ble', 'BLE蓝牙通信/BTDMSpliter'),
            'ble': ('cil/ble', 'BLE蓝牙通信'),
            'bt': ('cil/ble', 'BLE蓝牙通信'),
            'btstack': ('cil/ble', 'BLE蓝牙通信/BTstack'),
            'hci': ('cil/ble', 'BLE蓝牙通信/HCI层'),
            'l2cap': ('cil/ble', 'BLE蓝牙通信/L2CAP层'),
            'rfcomm': ('cil/ble', 'BLE蓝牙通信/RFCOMM'),
            'sdp': ('cil/ble', 'BLE蓝牙通信/SDP服务发现'),
            'can': ('can/vehicle', 'CAN总线/整车通信'),
            'vehicle': ('can/vehicle', '整车控制/Vehicle'),
            'atdev': ('atdev/uart', 'AT设备/UART通信'),
            'driver': ('atdev/uart', 'BSP驱动/UART通信'),
            'bsp': ('atdev/uart', 'BSP驱动/外设驱动'),
            'display': ('atdev/uart', '显示驱动/Display'),
            'touchpad': ('atdev/uart', '触控驱动/Touchpad'),
            'flash': ('atdev/uart', '存储驱动/Flash'),
            'lwip': ('atdev/uart', '网络协议栈/LwIP'),
            'mos': ('mos/ota', 'MOS升级/固件管理'),
            'ota': ('mos/ota', 'MOS升级/OTA更新'),
            'apptools': ('apptools/app', '应用工具层'),
            'common': ('apptools/app', '公共代码/Common'),
            'proj': ('apptools/app', '项目工程/Project'),
            'task_statistic': ('task_statistic/metric', '任务统计/性能指标'),
            'modules': ('apptools/app', '应用模块/Modules'),
        }

        for keyword, (subsystem, context) in subsystem_map.items():
            if keyword in path_lower:
                return subsystem, context

        return ('unknown', '未分类代码')

    def process_directory(self, force: bool = False) -> dict:
        """处理整个目录，返回所有图的汇总"""
        all_nodes = []
        all_edges = []
        processed_files = 0
        errors = []

        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['build', 'output', '.git']]

            for file in files:
                if not file.endswith(('.c', '.h')):
                    continue

                file_path = os.path.join(root, file)
                try:
                    graph = self.extract_from_file(file_path)

                    for node in graph['nodes']:
                        node['file'] = file_path.replace('\\', '/')

                    all_nodes.extend(graph['nodes'])
                    all_edges.extend(graph['edges'])
                    processed_files += 1

                    self.graphs[file_path] = graph

                except Exception as e:
                    errors.append(f"{file}: {str(e)}")
                    import sys
                    print(f"[GraphExtractor] Error processing {file}: {e}", file=sys.stderr)

        return {
            "nodes": all_nodes,
            "edges": all_edges,
            "files_processed": processed_files,
            "total_nodes": len(all_nodes),
            "total_edges": len(all_edges),
            "errors": errors if errors else None
        }

    def save_graph(self, output_dir: str = "knowledge_base/parsed/graph"):
        """保存图数据到JSON文件"""
        os.makedirs(output_dir, exist_ok=True)

        for file_path, graph in self.graphs.items():
            safe_name = hashlib.md5(file_path.encode()).hexdigest()[:12]
            output_path = os.path.join(output_dir, f"{safe_name}.json")

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(graph, f, ensure_ascii=False, indent=2)

            print(f"[GraphExtractor] Saved: {os.path.basename(file_path)} -> {safe_name}.json")

    def search_functions_by_name(self, name: str) -> List[GraphNode]:
        """搜索函数名匹配的节点"""
        results = []
        for graph in self.graphs.values():
            for node in graph['nodes']:
                if node['type'] == 'function' and name.lower() in node['name'].lower():
                    results.append(GraphNode(**node))
        return results

    def get_callers(self, func_name: str) -> List[str]:
        """获取调用指定函数的所有函数"""
        callers = []
        for graph in self.graphs.values():
            for edge in graph['edges']:
                if edge['to_node'] == f"func:{func_name}" and edge['edge_type'] == 'calls':
                    callers.append(edge['from_node'])
        return list(set(callers))

    def get_callees(self, func_name: str) -> List[str]:
        """获取指定函数调用的所有函数"""
        callees = []
        for graph in self.graphs.values():
            for edge in graph['edges']:
                if edge['from_node'] == f"func:{func_name}" and edge['edge_type'] == 'calls':
                    callees.append(edge['to_node'])
        return list(set(callees))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    print("=== C代码图关系提取 (Tree-sitter) ===")
    extractor = CodeGraphExtractor("knowledge_base/raw/c_code")
    result = extractor.process_directory()

    print(f"Files: {result['files_processed']}")
    print(f"Nodes: {result['total_nodes']}")
    print(f"Edges: {result['total_edges']}")
    if result['errors']:
        print(f"Errors: {len(result['errors'])}")

    extractor.save_graph()
    print("Graph saved to knowledge_base/parsed/graph/")