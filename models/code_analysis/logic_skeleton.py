import re
import os
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


class StateMachineType(Enum):
    SWITCH_CASE = "switch_case"
    TABLE_DRIVEN = "table_driven"
    FLAG_BASED = "flag_based"


@dataclass
class StateTransition:
    from_state: str
    to_state: str
    condition: str
    action: str
    event: Optional[str] = None


@dataclass
class StateMachineInfo:
    name: str
    type: StateMachineType
    states: List[str]
    transitions: List[StateTransition]
    initial_state: str
    file_path: str
    line_number: int
    description: str = ""


@dataclass
class BranchLogic:
    condition: str
    true_branch: str
    false_branch: Optional[str]
    nesting_level: int
    line_number: int


@dataclass
class ProtocolFlow:
    name: str
    steps: List[Dict[str, str]]
    file_path: str
    line_number: int
    description: str = ""


class LogicSkeletonExtractor:
    SWITCH_PATTERN = re.compile(
        r'switch\s*\(\s*(\w+)\s*\)\s*\{',
        re.MULTILINE
    )

    CASE_PATTERN = re.compile(
        r'case\s+(\w+)\s*:',
        re.MULTILINE
    )

    DEFAULT_PATTERN = re.compile(
        r'default\s*:',
        re.MULTILINE
    )

    IF_PATTERN = re.compile(
        r'if\s*\(\s*([^)]+)\s*\)',
        re.MULTILINE
    )

    ELSE_IF_PATTERN = re.compile(
        r'else\s+if\s*\(\s*([^)]+)\s*\)',
        re.MULTILINE
    )

    ELSE_PATTERN = re.compile(
        r'else\s*\{',
        re.MULTILINE
    )

    FUNCTION_PATTERN = re.compile(
        r'((?:static\s+|extern\s+)?(?:\w+\s+)*?\w+\s*\*?\s*(\w+)\s*\([^)]*\)\s*\{)',
        re.MULTILINE
    )

    def __init__(self, source_dir: str):
        self.source_dir = source_dir
        self.state_machines: List[StateMachineInfo] = []
        self.protocol_flows: List[ProtocolFlow] = []

    def extract_from_file(self, file_path: str) -> List[StateMachineInfo]:
        state_machines = []

        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()

            state_machines = self._extract_state_machines(content, file_path)

        except Exception as e:
            print(f"Error extracting logic skeletons from {file_path}: {e}")

        return state_machines

    def _extract_state_machines(self, content: str, file_path: str) -> List[StateMachineInfo]:
        state_machines = []

        for switch_match in self.SWITCH_PATTERN.finditer(content):
            switch_var = switch_match.group(1)
            switch_start = switch_match.end()
            switch_line = content[:switch_match.start()].count('\n') + 1

            brace_count = 1
            switch_end = switch_start
            for i, c in enumerate(content[switch_start:], switch_start):
                if c == '{':
                    brace_count += 1
                elif c == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        switch_end = i
                        break

            switch_body = content[switch_start:switch_end]

            cases = []
            for case_match in self.CASE_PATTERN.finditer(switch_body):
                case_name = case_match.group(1)
                case_offset = switch_start + case_match.start()
                case_line = content[:case_offset].count('\n') + 1
                cases.append((case_name, case_line))

            has_default = bool(self.DEFAULT_PATTERN.search(switch_body))

            if len(cases) >= 2:
                transitions = []
                states = [c[0] for c in cases]

                for i, (case_name, case_line) in enumerate(cases):
                    action = self._extract_case_action(switch_body, case_match.start())

                    if i < len(cases) - 1:
                        next_case_name = cases[i + 1][0]
                        transitions.append(StateTransition(
                            from_state=case_name,
                            to_state=next_case_name,
                            condition=f"case {case_name}",
                            action=action,
                            event=switch_var
                        ))
                    elif has_default:
                        transitions.append(StateTransition(
                            from_state=case_name,
                            to_state="default",
                            condition=f"case {case_name}",
                            action=action,
                            event=switch_var
                        ))

                initial_state = cases[0][0] if cases else ""

                sm_info = StateMachineInfo(
                    name=f"state_machine_{switch_var}",
                    type=StateMachineType.SWITCH_CASE,
                    states=states,
                    transitions=transitions,
                    initial_state=initial_state,
                    file_path=file_path,
                    line_number=switch_line,
                    description=f"状态机: switch({switch_var}), 共{len(cases)}个状态"
                )
                state_machines.append(sm_info)
                self.state_machines.append(sm_info)

        return state_machines

    def _extract_case_action(self, switch_body: str, case_offset: int) -> str:
        case_content_start = switch_body.find(':', case_offset)
        next_case = switch_body.find('case ', case_content_start + 1)
        next_default = switch_body.find('default', case_content_start + 1)

        end_pos = len(switch_body)
        if next_case > 0:
            end_pos = min(end_pos, next_case)
        if next_default > 0:
            end_pos = min(end_pos, next_default)

        action_content = switch_body[case_content_start + 1:end_pos]
        action_lines = [line.strip() for line in action_content.split('\n') if line.strip() and not line.strip().startswith('case')]

        if len(action_lines) <= 3:
            return ' '.join(action_lines[:2])
        else:
            return action_lines[0] if action_lines else ""

    def extract_branch_logic(self, content: str, file_path: str) -> List[BranchLogic]:
        branches = []

        lines = content.split('\n')
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            if_match = self.IF_PATTERN.search(line)
            if if_match:
                condition = if_match.group(1)
                nesting = 0
                for j in range(i):
                    if '{' in lines[j]:
                        nesting += lines[j].count('{')
                    if '}' in lines[j]:
                        nesting -= lines[j].count('}')

                true_branch = ""
                false_branch = None

                brace_count = 0
                block_start = i
                j = i
                found_open = False
                while j < len(lines):
                    if '{' in lines[j]:
                        found_open = True
                        brace_count += lines[j].count('{')
                    if '}' in lines[j]:
                        brace_count -= lines[j].count('}')
                    if found_open and brace_count == 0:
                        block_end = j
                        break
                    j += 1

                if found_open:
                    block_content = '\n'.join(lines[block_start:block_end + 1])
                    true_branch = self._summarize_block(block_content)
                else:
                    true_branch = lines[i + 1].strip() if i + 1 < len(lines) else ""

                if j + 1 < len(lines):
                    next_line = lines[j + 1].strip()
                    if next_line.startswith('else'):
                        if next_line.startswith('else if'):
                            else_if_match = self.ELSE_IF_PATTERN.search(next_line)
                            if else_if_match:
                                false_branch = f"else if ({else_if_match.group(1)}) ..."
                        elif next_line.startswith('else'):
                            false_branch = "else ..."

                branches.append(BranchLogic(
                    condition=condition,
                    true_branch=true_branch,
                    false_branch=false_branch,
                    nesting_level=nesting,
                    line_number=i + 1
                ))

            i += 1

        return branches

    def _summarize_block(self, block_content: str) -> str:
        lines = [l.strip() for l in block_content.split('\n') if l.strip() and not l.strip().startswith('{') and not l.strip().startswith('}')]

        actions = []
        for line in lines[:3]:
            line = re.sub(r'\s+', ' ', line)
            if 'return' in line:
                actions.append(f"返回: {self._extract_return_value(line)}")
            elif 'send' in line.lower() or 'transmit' in line.lower():
                actions.append("发送数据")
            elif 'set' in line.lower() or 'update' in line.lower():
                actions.append("更新状态")
            elif 'check' in line.lower() or 'verify' in line.lower():
                actions.append("校验")
            elif 'init' in line.lower():
                actions.append("初始化")
            else:
                actions.append(line[:50] if len(line) > 50 else line)

        return '; '.join(actions) if actions else "处理"

    def _extract_return_value(self, line: str) -> str:
        return_match = re.search(r'return\s*(.+?);', line)
        if return_match:
            val = return_match.group(1).strip()
            if val.isdigit():
                return f"值 {val}"
            return val[:30]
        return "void"

    def detect_protocol_flow(self, content: str, file_path: str) -> List[ProtocolFlow]:
        flows = []

        func_pattern = re.compile(
            r'(?:static\s+)?(?:\w+\s+)*?\w+\s*\*?\s*(\w+)\s*\([^)]*\)\s*\{',
            re.MULTILINE
        )

        protocol_keywords = ['protocol', 'frame', 'packet', 'handle', 'process', 'parse', 'encode', 'decode']

        for func_match in func_pattern.finditer(content):
            func_name = func_match.group(1)

            if any(kw in func_name.lower() for kw in protocol_keywords):
                func_start = func_match.start()
                func_line = content[:func_start].count('\n') + 1

                brace_count = 0
                func_end = func_start
                found_open = False
                for i, c in enumerate(content[func_start:], func_start):
                    if c == '{':
                        found_open = True
                        brace_count += 1
                    elif c == '}':
                        brace_count -= 1
                        if found_open and brace_count == 0:
                            func_end = i
                            break

                if brace_count == 0 or not found_open:
                    func_content = content[func_match.start():func_match.start() + 500]
                else:
                    func_content = content[func_match.start():func_end + 1]

                steps = self._extract_protocol_steps(func_content)

                if len(steps) >= 2:
                    flow = ProtocolFlow(
                        name=func_name,
                        steps=steps,
                        file_path=file_path,
                        line_number=func_line,
                        description=f"协议处理流程: {func_name}"
                    )
                    flows.append(flow)
                    self.protocol_flows.append(flow)

        return flows

    def _extract_protocol_steps(self, content: str) -> List[Dict[str, str]]:
        steps = []

        step_keywords = {
            'check': '检查',
            'parse': '解析',
            'decode': '解码',
            'encode': '编码',
            'validate': '验证',
            'send': '发送',
            'receive': '接收',
            'update': '更新',
            'set': '设置',
            'get': '获取',
            'copy': '复制',
            'fill': '填充',
            'calculate': '计算'
        }

        lines = content.split('\n')
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if not line_stripped or line_stripped.startswith('//') or line_stripped.startswith('/*'):
                continue

            for keyword, action_cn in step_keywords.items():
                if re.search(rf'\b{keyword}\w*\b', line_stripped, re.IGNORECASE):
                    var_match = re.search(r'(\w+)\s*=', line_stripped)
                    var_name = var_match.group(1) if var_match else ""

                    steps.append({
                        'order': len(steps) + 1,
                        'action': action_cn,
                        'detail': line_stripped[:80],
                        'line_offset': i
                    })
                    break

        return steps[:10]

    def extract_from_directory(self) -> Dict[str, List]:
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith(('.c', '.h')):
                    file_path = os.path.join(root, file)
                    self.extract_from_file(file_path)

        return {
            'state_machines': [self._sm_to_dict(sm) for sm in self.state_machines],
            'protocol_flows': [self._pf_to_dict(pf) for pf in self.protocol_flows]
        }

    def _sm_to_dict(self, sm: StateMachineInfo) -> Dict:
        return {
            'name': sm.name,
            'type': sm.type.value,
            'states': sm.states,
            'initial_state': sm.initial_state,
            'transitions': [
                {
                    'from': t.from_state,
                    'to': t.to_state,
                    'condition': t.condition,
                    'action': t.action,
                    'event': t.event
                }
                for t in sm.transitions
            ],
            'file': sm.file_path,
            'line': sm.line_number,
            'description': sm.description
        }

    def _pf_to_dict(self, pf: ProtocolFlow) -> Dict:
        return {
            'name': pf.name,
            'steps': pf.steps,
            'file': pf.file_path,
            'line': pf.line_number,
            'description': pf.description
        }