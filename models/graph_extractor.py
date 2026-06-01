"""
Code Graph Extractor using pycparser
基于AST的C代码函数调用图/关系图提取器
"""
import os
import re
import json
import hashlib
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field, asdict

from pycparser import c_parser, c_ast, c_generator


@dataclass
class GraphNode:
    id: str
    type: str  # function, variable, struct, enum, typedef, call
    name: str
    code_snippet: str = ""
    file: str = ""
    line_start: int = 0
    line_end: int = 0
    metadata: Dict = field(default_factory=dict)


@dataclass
class GraphEdge:
    from_node: str
    to_node: str
    edge_type: str  # calls, accesses, includes, defines
    metadata: Dict = field(default_factory=dict)


class FunctionExtractor(c_ast.NodeVisitor):
    """遍历AST提取函数定义"""

    def __init__(self, file_name: str):
        self.file_name = file_name
        self.nodes: List[GraphNode] = []
        self.func_names: Set[str] = set()

    def visit_FuncDef(self, node):
        decl = node.decl
        func_name = decl.name
        self.func_names.add(func_name)

        # 获取函数体代码片段
        generator = c_generator.CGenerator()
        func_code = generator.visit(node)

        # 获取行号 (pycparser 2.21 uses .coords, older uses .location)
        line_start = 0
        if hasattr(decl, 'coords') and decl.coords:
            line_start = decl.coords.line
        elif hasattr(decl, 'location') and decl.location:
            line_start = decl.location.get('line', 0) if isinstance(decl.location, dict) else decl.location.line

        line_end = line_start + func_code.count('\n')

        node_id = f"func:{func_name}"
        graph_node = GraphNode(
            id=node_id,
            type="function",
            name=func_name,
            code_snippet=func_code[:800],
            file=self.file_name,
            line_start=line_start,
            line_end=line_end,
            metadata={
                "params": self._get_params(decl),
                "decl": generator.visit(decl)
            }
        )
        self.nodes.append(graph_node)

    def visit_FuncDecl(self, node):
        pass  # 只处理定义，不处理声明

    def _get_params(self, decl) -> str:
        if hasattr(decl, 'params') and decl.params:
            params = []
            for p in decl.params.params:
                if hasattr(p, 'name') and p.name:
                    params.append(p.name)
                else:
                    params.append("...")
            return ", ".join(params)
        return ""


class VariableExtractor(c_ast.NodeVisitor):
    """遍历AST提取全局变量"""

    def __init__(self, file_name: str, func_names: Set[str] = None):
        self.file_name = file_name
        self.func_names = func_names or set()
        self.nodes: List[GraphNode] = []
        self.in_function: bool = False
        self.brace_depth: int = 0

    def visit_FileAST(self, node):
        self.generic_visit(node)

    def visit_FuncDef(self, node):
        self.brace_depth = 0
        self.in_function = True
        self.generic_visit(node)
        self.in_function = False
        self.brace_depth = 0

    def visit_Typedecl(self, node):
        if self.brace_depth == 0 and not self.in_function:
            node_id = f"type:{node.name}"
            graph_node = GraphNode(
                id=node_id,
                type="typedef",
                name=node.name,
                code_snippet=node.name,
                file=self.file_name,
                metadata={"decl": node.name}
            )
            self.nodes.append(graph_node)

    def visit_Decl(self, node):
        if not self.in_function and not self.func_names:
            # 全局变量
            if hasattr(node, 'name') and node.name:
                node_id = f"var:{node.name}"
                graph_node = GraphNode(
                    id=node_id,
                    type="variable",
                    name=node.name,
                    code_snippet=node.name,
                    file=self.file_name,
                    metadata={"decl": "global"}
                )
                self.nodes.append(graph_node)

    def visit_Struct(self, node):
        if node.name:
            node_id = f"struct:{node.name}"
            graph_node = GraphNode(
                id=node_id,
                type="struct",
                name=node.name,
                code_snippet=node.name,
                file=self.file_name,
                metadata={"fields": self._get_struct_fields(node)}
            )
            self.nodes.append(graph_node)

    def visit_Union(self, node):
        if node.name:
            node_id = f"union:{node.name}"
            graph_node = GraphNode(
                id=node_id,
                type="union",
                name=node.name,
                code_snippet=node.name,
                file=self.file_name,
                metadata={"fields": self._get_struct_fields(node)}
            )
            self.nodes.append(graph_node)

    def visit_Enum(self, node):
        if node.name:
            node_id = f"enum:{node.name}"
            graph_node = GraphNode(
                id=node_id,
                type="enum",
                name=node.name,
                code_snippet=node.name,
                file=self.file_name,
                metadata={"values": self._get_enum_values(node)}
            )
            self.nodes.append(graph_node)

    def _get_struct_fields(self, node) -> List[str]:
        if hasattr(node, 'members') and node.members:
            return [getattr(m, 'name', '') for m in node.members]
        return []

    def _get_enum_values(self, node) -> List[str]:
        values = []
        if hasattr(node, 'values') and node.values:
            if hasattr(node.values, 'enumerators'):
                for c in node.values.enumerators:
                    if hasattr(c, 'name'):
                        values.append(c.name)
        return values


class CallExtractor(c_ast.NodeVisitor):
    """遍历AST提取函数调用关系"""

    def __init__(self, file_name: str, func_names: Set[str] = None, all_known_funcs: Set[str] = None):
        self.file_name = file_name
        self.func_names = func_names or set()
        self.all_known_funcs = all_known_funcs or set()
        self.edges: List[GraphEdge] = []
        self.current_func: Optional[str] = None
        self.in_function: bool = False

    def visit_FuncDef(self, node):
        self.current_func = node.decl.name
        self.in_function = True
        self.generic_visit(node)
        self.in_function = False
        self.current_func = None

    def visit_FuncCall(self, node):
        if self.current_func and self.in_function:
            callee_name = None
            if hasattr(node, 'name') and hasattr(node.name, 'name'):
                callee_name = node.name.name

            if callee_name:
                # 确定边的目标节点类型
                if callee_name in self.all_known_funcs:
                    to_node = f"func:{callee_name}"
                else:
                    to_node = f"ext:{callee_name}"

                from_node = f"func:{self.current_func}"
                edge = GraphEdge(
                    from_node=from_node,
                    to_node=to_node,
                    edge_type="calls",
                    metadata={"callee": callee_name}
                )
                self.edges.append(edge)

        self.generic_visit(node)


class CodeGraphExtractor:
    """C代码图关系提取器主类"""

    # 内置函数列表
    BUILTIN_FUNCS = {
        'printf', 'scanf', 'malloc', 'free', 'memcpy', 'memset', 'strlen',
        'strcpy', 'strncpy', 'strcmp', 'memcmp', 'memmove', 'sprintf',
        'snprintf', 'atoi', 'atof', 'strtol', 'strdup', 'calloc',
        'realloc', 'exit', 'abort', 'assert', 'sizeof', 'offsetof',
        'vsprintf', 'vprintf', 'sscanf', 'strcat', 'strncat', 'memchr',
        'localtime', 'gmtime', 'time', 'srand', 'rand'
    }

    def __init__(self, source_dir: str = "knowledge_base/raw/c_code"):
        self.source_dir = source_dir
        self.parsed_files: Dict[str, float] = {}
        self.graphs: Dict[str, dict] = {}
        self.parser = c_parser.CParser()

    def extract_from_file(self, file_path: str) -> dict:
        """从C文件提取图结构"""
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        file_name = os.path.basename(file_path)

        try:
            # 解析C代码为AST
            ast = self.parser.parse(content, filename=file_name)
        except Exception as e:
            # 解析失败，尝试清理代码后重试
            cleaned = self._preprocess_c_code(content)
            try:
                ast = self.parser.parse(cleaned, filename=file_name)
            except Exception as e2:
                # 再次失败，可能是头文件或仅有声明，跳过
                return {"nodes": [], "edges": [], "file": file_name, "full_path": file_path, "total_lines": len(content.split('\n'))}

        # 提取节点
        func_extractor = FunctionExtractor(file_name)
        func_extractor.visit(ast)
        func_nodes = func_extractor.nodes
        func_names = func_extractor.func_names

        var_extractor = VariableExtractor(file_name, func_names)
        var_extractor.visit(ast)
        var_nodes = var_extractor.nodes

        # 提取调用关系边
        call_extractor = CallExtractor(file_name, func_names, func_names | self.BUILTIN_FUNCS)
        call_extractor.visit(ast)
        call_edges = call_extractor.edges

        # 添加struct/enum节点
        type_nodes = var_extractor.nodes

        all_nodes = func_nodes + type_nodes

        return {
            "nodes": [asdict(n) for n in all_nodes],
            "edges": [asdict(e) for e in call_edges],
            "file": file_name,
            "full_path": file_path,
            "total_lines": len(content.split('\n'))
        }

    def _preprocess_c_code(self, content: str) -> str:
        """预处理C代码，使pycparser可以解析"""
        # 移除 /* */ 多行注释
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # 移除 // 单行注释
        content = re.sub(r'//.*$', '', content, flags=re.MULTILINE)

        lines = content.split('\n')
        processed_lines = []

        # 常见标准头文件的存根定义
        stub_defs = [
            'typedef unsigned int uint32_t;',
            'typedef unsigned short uint16_t;',
            'typedef unsigned char uint8_t;',
            'typedef int int32_t;',
            'typedef short int16_t;',
            'typedef signed char int8_t;',
            'typedef unsigned long uintptr_t;',
            'typedef unsigned long ulong;',
            'typedef unsigned char uchar;',
            'typedef unsigned short ushort;',
            'typedef unsigned int uint;',
            'typedef char CHAR;',
            'typedef unsigned char UCHAR;',
            'typedef uint8_t bool_t;',
            'typedef long off_t;',
            'typedef long ssize_t;',
            'typedef unsigned long size_t;',
        ]

        for line in lines:
            stripped = line.strip()

            # 跳过 #include
            if stripped.startswith('#include'):
                continue

            # 跳过简单的 #define 常量
            if stripped.startswith('#define'):
                if re.match(r'#define\s+\w+\s+\d+', stripped):
                    continue
                continue

            # 跳过 #pragma
            if stripped.startswith('#pragma'):
                continue

            # 跳过其他预编译指令
            if stripped.startswith('#'):
                continue

            # 移除 __attribute__
            if '__attribute__' in stripped:
                stripped = re.sub(r'__attribute__\s*\(\([^)]*\)\)', '', stripped)

            # 移除未知的关键字/属性（如 __RAM_CODE 等属性标记）
            if '__' in stripped:
                stripped = re.sub(r'__[A-Z_]+\s+', '', stripped)  # 移除前缀如 "__RAM_CODE "
                stripped = stripped.strip()
                # 如果只剩下 __xxx 形式的标识符，直接移除整行（这通常是宏调用）
                if stripped.startswith('__') or stripped == '()':
                    continue

            # 替换 __builtin 开头的函数
            if '__builtin_' in stripped:
                stripped = re.sub(r'__builtin_[a-zA-Z_]+', '0', stripped)

            # 处理常见类型定义
            stripped = stripped.replace('uint8_t', 'unsigned char')
            stripped = stripped.replace('uint16_t', 'unsigned short')
            stripped = stripped.replace('uint32_t', 'unsigned int')
            stripped = stripped.replace('uint64_t', 'unsigned long long')
            stripped = stripped.replace('int8_t', 'signed char')
            stripped = stripped.replace('int16_t', 'short')
            stripped = stripped.replace('int32_t', 'int')
            stripped = stripped.replace('int64_t', 'long long')
            stripped = stripped.replace('bool_t', 'int')
            stripped = stripped.replace('CHAR', 'char')
            stripped = stripped.replace('UCHAR', 'unsigned char')
            stripped = stripped.replace('uintptr_t', 'unsigned long')
            stripped = stripped.replace('size_t', 'unsigned long')
            stripped = stripped.replace('ssize_t', 'long')
            stripped = stripped.replace('off_t', 'long')
            stripped = stripped.replace('HANDLE', 'void*')
            stripped = stripped.replace('BOOL', 'int')
            stripped = stripped.replace('DWORD', 'unsigned int')
            stripped = stripped.replace('WORD', 'unsigned short')
            stripped = stripped.replace('BYTE', 'unsigned char')
            stripped = stripped.replace('LPSTR', 'char*')
            stripped = stripped.replace('LPCSTR', 'const char*')
            stripped = stripped.replace('TRUE', '1')
            stripped = stripped.replace('FALSE', '0')
            stripped = stripped.replace('NULL', '0')
            stripped = stripped.replace('nullptr', '0')

            # 处理结构体指针箭头访问（简化复杂表达式）
            if '->' in stripped and ('(' in stripped or '*' in stripped):
                parts = stripped.split('->')
                if len(parts) > 2:
                    stripped = parts[0] + '->' + parts[-1]

            # 跳过汇编内联
            if '__asm' in stripped or '__asm__' in stripped:
                continue

            # 处理函数指针类型
            if 'typedef' in stripped and '(*)' in stripped:
                stripped = re.sub(r'\(\*[^)A-Za-z]+\)', '(fp)', stripped)

            processed_lines.append(stripped)

        # 添加存根定义（包括自动检测的未知类型）
        stub = '\n'.join(stub_defs)

        # 扫描代码中的未知类型并生成前向声明
        # 只匹配看起来像结构体/句柄类型的标识符（必须是CamelCase且包含特定关键词）
        unknown_types = set()
        # 匹配 CamelCase 类型名（包含 Handle, Def, Config, Mode, State, Event, Status, IRQ, EN, INT, TYPE, SEL, SRC 等关键词）
        # 变量名通常是 snake_case，不会被此模式匹配
        type_pattern = re.compile(r'\b([A-Z][a-z]+(?:[A-Z][a-z]+)*(?:Handle|Def|Config|Mode|State|Event|Status|IRQ|EN|INT|Type|Sel|Src)[A-Za-z_]*)\b')
        for line in lines:
            for match in type_pattern.finditer(line):
                t = match.group(1)
                # 跳过已知类型
                if t not in {'uint32_t', 'uint16_t', 'uint8_t', 'int32_t', 'int16_t', 'int8_t',
                            'size_t', 'ssize_t', 'off_t', 'FILE', 'BOOL', 'DWORD', 'WORD', 'BYTE',
                            'HANDLE', 'LPSTR', 'LPCSTR', 'CALI_HandleTypeDef'}:
                    unknown_types.add(t)

        # 常见嵌入式类型的存根
        embedded_stubs = [
            'struct CALI_HandleTypeDef { int _dummy; }; typedef struct CALI_HandleTypeDef CALI_HandleTypeDef;',
            'struct TaskHandle_t { int _dummy; }; typedef struct TaskHandle_t TaskHandle_t;',
            'struct UBaseType_t { int _dummy; }; typedef struct TaskHandle_t UBaseType_t;',
            'struct GPIO_TypeDef { int _dummy; }; typedef struct GPIO_TypeDef GPIO_TypeDef;',
            'struct EXTI_TYPE { int _dummy; }; typedef struct EXTI_TYPE EXTI_TYPE;',
            'struct OspiPadConfig { int _dummy; }; typedef struct OspiPadConfig OspiPadConfig;',
            'struct QspiPadConfig { int _dummy; }; typedef struct QspiPadConfig QspiPadConfig;',
            'struct System_ClkConfig_t { int _dummy; }; typedef struct System_ClkConfig_t System_ClkConfig_t;',
            'struct SPLL_CFG_t { int _dummy; }; typedef struct SPLL_CFG_t SPLL_CFG_t;',
            'struct MCU_Clock_Source_t { int _dummy; }; typedef struct MCU_Clock_Source_t MCU_Clock_Source_t;',
            'struct SOC_DIV_t { int _dummy; }; typedef struct SOC_DIV_t SOC_DIV_t;',
        ]

        for t in sorted(unknown_types):
            stub += f'\nstruct {t} {{ int _dummy; }}; typedef struct {t} {t};'

        for s in embedded_stubs:
            stub += f'\n{s}'

        return stub + '\n' + '\n'.join(processed_lines)

    def _is_in_string(self, line: str, pos: int) -> bool:
        """检查指定位置是否在字符串内"""
        in_string = False
        for i, c in enumerate(line):
            if c == '"' and (i == 0 or line[i-1] != '\\'):
                in_string = not in_string
            if i == pos:
                return in_string
        return in_string

    def process_directory(self, force: bool = False) -> dict:
        """处理整个目录，返回所有图的汇总"""
        all_nodes = []
        all_edges = []
        processed_files = 0
        errors = []

        for root, dirs, files in os.walk(self.source_dir):
            # 跳过隐藏目录和构建目录
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['build', 'output', '.git']]

            for file in files:
                if not file.endswith(('.c', '.h')):
                    continue

                file_path = os.path.join(root, file)
                try:
                    graph = self.extract_from_file(file_path)

                    # 更新节点的文件路径为完整路径
                    for node in graph['nodes']:
                        node['file'] = file_path.replace('\\', '/')

                    all_nodes.extend(graph['nodes'])
                    all_edges.extend(graph['edges'])
                    processed_files += 1

                    self.graphs[file_path] = graph

                except Exception as e:
                    errors.append(f"{file}: {str(e)}")
                    print(f"[GraphExtractor] Error processing {file}: {e}")

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


class DPProtocolRelationExtractor:
    """提取DP数据点与CAN协议的关系"""

    def __init__(self, kb_path: str = "knowledge_base/raw/protocol_docs"):
        self.kb_path = kb_path
        self.dp_can_relations: List[dict] = []

    def extract_from_protocol(self, file_path: str) -> List[dict]:
        """从协议文档提取DP和CAN的映射关系"""
        relations = []

        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        dp_pattern = r'DP\s*[:.]?\s*(\d+)|DP\s*ID\s*[:.\s]*0x([0-9A-Fa-f]+)|dp[_\s]*(id|data)'
        can_pattern = r'0x([0-9A-Fa-f]{4,8})|CAN\s*(ID|报文|帧)|PGN\s*[:.\s]*0x([0-9A-Fa-f]+)'

        dp_matches = list(re.finditer(dp_pattern, content, re.IGNORECASE))
        can_matches = list(re.finditer(can_pattern, content, re.IGNORECASE))

        for dp_match in dp_matches:
            dp_value = dp_match.group(1) or dp_match.group(2) or "unknown"
            dp_context = content[max(0, dp_match.start()-50):dp_match.end()+50]

            related_cans = []
            for can_match in can_matches:
                if abs(can_match.start() - dp_match.start()) < 200:
                    can_value = can_match.group(1) or can_match.group(3) or "unknown"
                    related_cans.append(can_value)

            relations.append({
                "dp_id": dp_value,
                "context": dp_context.replace('\n', ' ').strip(),
                "related_can_ids": related_cans,
                "source_file": os.path.basename(file_path)
            })

        self.dp_can_relations.extend(relations)
        return relations

    def process_all_protocols(self) -> List[dict]:
        """处理所有协议文档"""
        all_relations = []

        for file in os.listdir(self.kb_path):
            ext = os.path.splitext(file)[1].lower()
            if ext in {'.pdf', '.md', '.txt'}:
                file_path = os.path.join(self.kb_path, file)
                try:
                    relations = self.extract_from_protocol(file_path)
                    all_relations.extend(relations)
                except Exception as e:
                    print(f"Error processing {file}: {e}")

        return all_relations

    def save_relations(self, output_path: str = "knowledge_base/parsed/graph/dp_can_relations.json"):
        """保存DP-CAN关系"""
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.dp_can_relations, f, ensure_ascii=False, indent=2)
        print(f"[DPProtocolExtractor] Saved {len(self.dp_can_relations)} relations to {output_path}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

    print("=== C代码图关系提取 (pycparser) ===")
    extractor = CodeGraphExtractor("knowledge_base/raw/c_code")
    result = extractor.process_directory()

    print(f"Files: {result['files_processed']}")
    print(f"Nodes: {result['total_nodes']}")
    print(f"Edges: {result['total_edges']}")
    if result['errors']:
        print(f"Errors: {len(result['errors'])}")

    extractor.save_graph()
    print("Graph saved to knowledge_base/parsed/graph/")

    print("\n=== DP-CAN关系提取 ===")
    dp_extractor = DPProtocolRelationExtractor()
    relations = dp_extractor.process_all_protocols()
    print(f"DP-CAN relations: {len(relations)}")
    dp_extractor.save_relations()