import re
import os
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class FunctionNode:
    name: str
    file_path: str
    line_number: int
    calls: List[str] = field(default_factory=list)
    called_by: List[str] = field(default_factory=list)
    is_exported: bool = False
    is_static: bool = False


@dataclass
class CallGraph:
    nodes: Dict[str, FunctionNode] = field(default_factory=dict)
    file_modules: Dict[str, List[str]] = field(default_factory=dict)

    def get_module_name(self, file_path: str) -> str:
        parts = file_path.replace('\\', '/').split('/')
        for part in reversed(parts):
            if part not in ['Src', 'Inc', 'components', 'modules', 'VL', 'driver']:
                return part.replace('.c', '').replace('.h', '')
        return 'unknown'

    def get_call_chain(self, start_func: str, max_depth: int = 3) -> List[List[str]]:
        chains = []
        visited = set()

        def dfs(func: str, path: List[str], depth: int):
            if depth >= max_depth or func in visited:
                return
            visited.add(func)
            path = path + [func]

            node = self.nodes.get(func)
            if node:
                if not node.calls:
                    chains.append(path)
                for called in node.calls:
                    if called in self.nodes:
                        dfs(called, path, depth + 1)

        dfs(start_func, [], 0)
        return chains

    def find_entry_points(self) -> List[str]:
        entry_points = []
        for name, node in self.nodes.items():
            if len(node.called_by) == 0 and node.calls:
                entry_points.append(name)
        return entry_points

    def find_leaf_functions(self) -> List[str]:
        leaf_funcs = []
        for name, node in self.nodes.items():
            if not node.calls and len(node.called_by) > 0:
                leaf_funcs.append(name)
        return leaf_funcs


class CallGraphExtractor:
    FUNCTION_PATTERN = re.compile(
        r'(?:static\s+)?(?:inline\s+)?(?:\w+\s+)*?\w+\s*\*?\s*(\w+)\s*\([^)]*\)\s*\{',
        re.MULTILINE
    )

    CALL_PATTERN = re.compile(
        r'\b(\w+)\s*\(',
        re.MULTILINE
    )

    STATIC_FUNC_PATTERN = re.compile(
        r'static\s+(?:inline\s+)?(?:\w+\s+)*?\w+\s*\*?\s*(\w+)\s*\([^)]*\)\s*\{',
        re.MULTILINE
    )

    EXTERN_FUNC_PATTERN = re.compile(
        r'(?:extern\s+)?(?:\w+\s+)*?\w+\s*\*?\s*(\w+)\s*\([^)]*\)\s*;',
        re.MULTILINE
    )

    INCLUDE_PATTERN = re.compile(r'#include\s*["<]([^">]+)[">]')

    def __init__(self, source_dir: str):
        self.source_dir = source_dir
        self.call_graph = CallGraph()
        self.header_declarations: Dict[str, Set[str]] = {}

    def extract_from_file(self, file_path: str) -> List[Tuple[str, str, int]]:
        calls = []
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            lines = content.split('\n')
            in_function = False
            current_func = None
            brace_count = 0
            func_start_line = 0

            for i, line in enumerate(lines, 1):
                stripped = line.strip()

                if not in_function:
                    func_match = re.search(self.FUNCTION_PATTERN, line)
                    if func_match:
                        func_name = func_match.group(1)
                        if not self._is_control_statement(func_name, stripped):
                            in_function = True
                            current_func = func_name
                            func_start_line = i
                            brace_count = 0
                else:
                    brace_count += stripped.count('{') - stripped.count('}')
                    if brace_count <= 0:
                        in_function = False
                        current_func = None
                        continue

                    for call_match in self.CALL_PATTERN.finditer(line):
                        called_func = call_match.group(1)
                        if not self._is_control_statement(called_func, stripped):
                            if called_func != current_func:
                                calls.append((current_func, called_func, i))

        except Exception as e:
            print(f"Error extracting calls from {file_path}: {e}")

        return calls

    def _is_control_statement(self, name: str, context: str) -> bool:
        control_keywords = {
            'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default',
            'break', 'continue', 'return', 'goto', 'sizeof', 'typeof',
            'true', 'false', 'NULL', 'nullptr'
        }
        if name in control_keywords:
            return True

        builtin_funcs = {
            'printf', 'sprintf', 'snprintf', 'scanf', 'sscanf',
            'malloc', 'calloc', 'realloc', 'free', 'memcpy', 'memset', 'memmove', 'memcmp',
            'strlen', 'strcpy', 'strncpy', 'strcat', 'strncat', 'strcmp', 'strncmp',
            'strchr', 'strrchr', 'strstr', 'strerror', 'atoi', 'atol', 'atof',
            'abs', 'labs', 'div', 'labs',
        }
        if name in builtin_funcs:
            return True

        return False

    def extract_from_directory(self) -> CallGraph:
        file_calls: Dict[str, List[Tuple[str, str, int]]] = {}

        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith(('.c', '.h')):
                    file_path = os.path.join(root, file)
                    calls = self.extract_from_file(file_path)
                    if calls:
                        file_calls[file_path] = calls

        self._build_graph(file_calls)
        return self.call_graph

    def _build_graph(self, file_calls: Dict[str, List[Tuple[str, str, int]]]):
        for file_path, calls in file_calls.items():
            module_name = self.call_graph.get_module_name(file_path)

            if module_name not in self.call_graph.file_modules:
                self.call_graph.file_modules[module_name] = []

            for caller, callee, line in calls:
                node_key = f"{caller}@{file_path}"

                if node_key not in self.call_graph.nodes:
                    self.call_graph.nodes[node_key] = FunctionNode(
                        name=caller,
                        file_path=file_path,
                        line_number=line,
                        is_static=file_path.endswith('.c')
                    )

                node = self.call_graph.nodes[node_key]
                if callee not in node.calls:
                    node.calls.append(callee)

                callee_key = callee
                if callee_key not in self.call_graph.nodes:
                    self.call_graph.nodes[callee_key] = FunctionNode(
                        name=callee,
                        file_path=file_path,
                        line_number=line
                    )

                callee_node = self.call_graph.nodes[callee_key]
                if caller not in callee_node.called_by:
                    callee_node.called_by.append(caller)

                if caller not in self.call_graph.file_modules[module_name]:
                    self.call_graph.file_modules[module_name].append(caller)

        self._resolve_external_calls()

    def _resolve_external_calls(self):
        all_func_names = {node.name for node in self.call_graph.nodes.values()}

        for node_key, node in self.call_graph.nodes.items():
            resolved_calls = []
            for called in node.calls:
                if called in all_func_names:
                    resolved_calls.append(called)
                else:
                    if called not in self.call_graph.nodes:
                        self.call_graph.nodes[called] = FunctionNode(
                            name=called,
                            file_path=node.file_path,
                            line_number=0,
                            is_exported=True
                        )

            node.calls = resolved_calls

    def get_protocol_related_functions(self) -> Dict[str, List[str]]:
        protocol_keywords = {
            'dp_', 'DP', 'ble_', 'BLE', 'can_', 'CAN',
            'ota_', 'OTA', 'mqtt_', 'MQTT', 'hid_', 'HID',
            'event', 'Event', 'frame', 'Frame', 'packet', 'Packet',
            'report', 'Report', 'upload', 'Upload',
            'callback', 'Callback', 'handler', 'Handler',
            'init', 'start', 'stop', 'process'
        }

        related = {}
        for module, funcs in self.call_graph.file_modules.items():
            protocol_funcs = [
                f for f in funcs
                if any(kw.lower() in f.lower() for kw in protocol_keywords)
            ]
            if protocol_funcs:
                related[module] = protocol_funcs

        return related

    def export_to_dict(self) -> Dict:
        return {
            'nodes': [
                {
                    'id': key,
                    'name': node.name,
                    'file': node.file_path,
                    'line': node.line_number,
                    'calls': node.calls,
                    'called_by': node.called_by,
                    'is_static': node.is_static,
                    'is_exported': node.is_exported
                }
                for key, node in self.call_graph.nodes.items()
            ],
            'modules': self.call_graph.file_modules,
            'entry_points': self.call_graph.find_entry_points(),
            'leaf_functions': self.call_graph.find_leaf_functions()
        }