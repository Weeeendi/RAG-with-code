import re
import os
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class StructInfo:
    name: str
    file_path: str
    line_number: int
    fields: List[Dict[str, str]]
    used_by_functions: List[str] = field(default_factory=list)


@dataclass
class EnumInfo:
    name: str
    file_path: str
    line_number: int
    values: List[Tuple[str, int]]
    used_by_functions: List[str] = field(default_factory=list)


@dataclass
class DPMapping:
    dp_id: str
    dp_name: str
    data_type: str
    handler_function: str
    related_struct: Optional[str] = None
    protocol_layer: str = "BLE"


@dataclass
class RelationshipGraph:
    structs: Dict[str, StructInfo] = field(default_factory=dict)
    enums: Dict[str, EnumInfo] = field(default_factory=dict)
    dp_mappings: Dict[str, DPMapping] = field(default_factory=dict)
    function_to_structs: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    struct_to_functions: Dict[str, List[str]] = field(default_factory=lambda: defaultdict(list))
    protocol_handlers: Dict[str, List[str]] = field(default_factory=dict)


class RelationshipMapper:
    STRUCT_PATTERN = re.compile(
        r'typedef\s+struct\s*(\w*)\s*\{([^}]+)\}\s*(\w+)\s*;',
        re.MULTILINE | re.DOTALL
    )

    STRUCT_FIELD_PATTERN = re.compile(
        r'(\w+)\s+(?:(?:\w+)\s+)?(\*?\s*\w+)\s*(?:\[(\d+)\])?\s*;',
        re.MULTILINE
    )

    ENUM_PATTERN = re.compile(
        r'typedef\s+enum\s*(\w*)\s*\{([^}]+)\}\s*(\w+)\s*;',
        re.MULTILINE | re.DOTALL
    )

    ENUM_VALUE_PATTERN = re.compile(
        r'(\w+)(?:\s*=\s*([^,}]+))?',
        re.MULTILINE
    )

    DPID_PATTERN = re.compile(r'DPID[_\w]*\s*=\s*0x([0-9A-Fa-f]+)', re.MULTILINE)
    DP_NAME_PATTERN = re.compile(r'["\'](\w+)["\']', re.MULTILINE)

    PROTOCOL_FRAME_PATTERN = re.compile(
        r'(?:typedef\s+)?struct\s+(\w*[Ff]rame\w*)\s*\{([^}]+)\}',
        re.MULTILINE | re.DOTALL
    )

    def __init__(self, source_dir: str):
        self.source_dir = source_dir
        self.relationship_graph = RelationshipGraph()

    def extract_from_file(self, file_path: str) -> Tuple[List[StructInfo], List[EnumInfo]]:
        structs = []
        enums = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            structs = self._extract_structs(content, file_path)
            enums = self._extract_enums(content, file_path)

        except Exception as e:
            print(f"Error extracting relationships from {file_path}: {e}")

        return structs, enums

    def _extract_structs(self, content: str, file_path: str) -> List[StructInfo]:
        structs = []

        for match in self.STRUCT_PATTERN.finditer(content):
            struct_body = match.group(2)
            line_number = content[:match.start()].count('\n') + 1

            fields = []
            for field_match in self.STRUCT_FIELD_PATTERN.finditer(struct_body):
                field_type = field_match.group(1)
                field_name = field_match.group(2).strip()
                field_array = field_match.group(3)

                field_info = {
                    'type': field_type,
                    'name': field_name,
                    'array_size': field_array
                }
                fields.append(field_info)

            name = match.group(3) or match.group(1) or "anonymous"

            struct_info = StructInfo(
                name=name,
                file_path=file_path,
                line_number=line_number,
                fields=fields
            )
            structs.append(struct_info)

            self.relationship_graph.structs[name] = struct_info

        return structs

    def _extract_enums(self, content: str, file_path: str) -> List[EnumInfo]:
        enums = []

        for match in self.ENUM_PATTERN.finditer(content):
            enum_body = match.group(2)
            line_number = content[:match.start()].count('\n') + 1

            values = []
            value_counter = 0
            for value_match in self.ENUM_VALUE_PATTERN.finditer(enum_body):
                value_name = value_match.group(1)
                value_expr = value_match.group(2)

                if value_expr:
                    try:
                        if '0x' in value_expr:
                            value_counter = int(value_expr.strip(), 16)
                        else:
                            value_counter = int(value_expr.strip())
                    except:
                        pass
                else:
                    value_counter += 1

                values.append((value_name, value_counter))

            name = match.group(3) or match.group(1) or "anonymous"

            enum_info = EnumInfo(
                name=name,
                file_path=file_path,
                line_number=line_number,
                values=values
            )
            enums.append(enum_info)

            self.relationship_graph.enums[name] = enum_info

        return enums

    def extract_from_directory(self) -> RelationshipGraph:
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith(('.c', '.h')):
                    file_path = os.path.join(root, file)
                    structs, enums = self.extract_from_file(file_path)

        self._map_struct_usage()
        self._map_dp_relationships()

        return self.relationship_graph

    def _map_struct_usage(self):
        struct_names = set(self.relationship_graph.structs.keys())

        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith(('.c', '.h')):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()

                        for struct_name in struct_names:
                            if struct_name in content:
                                func_pattern = re.compile(
                                    r'(?:static\s+)?(?:\w+\s+)*?\w+\s*\*?\s*(\w+)\s*\([^)]*\)',
                                    re.MULTILINE
                                )
                                for func_match in func_pattern.finditer(content):
                                    func_name = func_match.group(1)
                                    if not self._is_control_or_builtin(func_name):
                                        self.relationship_graph.function_to_structs[func_name].append(struct_name)
                                        self.relationship_graph.struct_to_functions[struct_name].append(func_name)

                                        if struct_name in self.relationship_graph.structs:
                                            self.relationship_graph.structs[struct_name].used_by_functions.append(func_name)

                    except Exception as e:
                        print(f"Error mapping struct usage in {file_path}: {e}")

    def _map_dp_relationships(self):
        dp_keywords = ['DPID', 'dp_id', 'datapoint', 'data_point', 'DP_']

        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith(('.c', '.h')):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()

                        if any(kw in content for kw in dp_keywords):
                            func_pattern = re.compile(
                                r'(?:static\s+)?(?:\w+\s+)*?\w+\s*\*?\s*(\w+)\s*\([^)]*\)',
                                re.MULTILINE
                            )
                            for func_match in func_pattern.finditer(content):
                                func_name = func_match.group(1)
                                if not self._is_control_or_builtin(func_name):
                                    if 'dp' in func_name.lower() or 'report' in func_name.lower():
                                        if func_name not in self.relationship_graph.protocol_handlers:
                                            self.relationship_graph.protocol_handlers[func_name] = []

                    except Exception as e:
                        print(f"Error mapping DP relationships in {file_path}: {e}")

    def _is_control_or_builtin(self, name: str) -> bool:
        control_keywords = {
            'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'default',
            'break', 'continue', 'return', 'goto', 'sizeof', 'typeof',
            'true', 'false', 'NULL', 'nullptr'
        }
        if name in control_keywords:
            return True

        builtin_funcs = {
            'printf', 'sprintf', 'snprintf', 'malloc', 'calloc', 'realloc', 'free',
            'memcpy', 'memset', 'memmove', 'memcmp', 'strlen', 'strcpy',
            'strcmp', 'strncmp', 'atoi', 'atol', 'abs', 'labs', 'div'
        }
        if name in builtin_funcs:
            return True

        return False

    def get_struct_for_dp(self, dp_name: str) -> Optional[str]:
        for struct_name, struct_info in self.relationship_graph.structs.items():
            if any(f['name'].lower() in dp_name.lower() or dp_name.lower() in f['name'].lower()
                   for f in struct_info.fields):
                return struct_name
        return None

    def get_functions_for_struct(self, struct_name: str) -> List[str]:
        return self.relationship_graph.struct_to_functions.get(struct_name, [])

    def get_related_handlers(self, dp_id: str) -> List[str]:
        related = []
        for handler, dplist in self.relationship_graph.protocol_handlers.items():
            if any(dp_id in str(dp) for dp in dplist):
                related.append(handler)
        return related

    def export_to_dict(self) -> Dict[str, Any]:
        return {
            'structs': [
                {
                    'name': s.name,
                    'file': s.file_path,
                    'line': s.line_number,
                    'fields': s.fields,
                    'used_by': s.used_by_functions
                }
                for s in self.relationship_graph.structs.values()
            ],
            'enums': [
                {
                    'name': e.name,
                    'file': e.file_path,
                    'line': e.line_number,
                    'values': e.values,
                    'used_by': e.used_by_functions
                }
                for e in self.relationship_graph.enums.values()
            ],
            'dp_mappings': [
                {
                    'dp_id': m.dp_id,
                    'dp_name': m.dp_name,
                    'data_type': m.data_type,
                    'handler': m.handler_function,
                    'related_struct': m.related_struct,
                    'protocol_layer': m.protocol_layer
                }
                for m in self.relationship_graph.dp_mappings.values()
            ],
            'function_struct_map': dict(self.relationship_graph.function_to_structs),
            'protocol_handlers': self.relationship_graph.protocol_handlers
        }