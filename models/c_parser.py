import os
import re
from typing import List, Dict, Any
from dataclasses import dataclass

from .utils.text_cleaner import EncodingConverter


@dataclass
class CodeBlock:
    file_path: str
    type: str
    name: str
    content: str
    line_number: int
    description: str = ""
    module: str = ""


MODULE_PATTERNS = {
    'OTA': r'(ota|upgrade|dfu|bootloader|固件|升级)',
    'BLE': r'(ble|bluetooth|hid|蓝牙|配对|绑定)',
    'CAN': r'(can|canbus|总线)',
    'RS485': r'(rs485|uart|串口)',
    'IoT': r'(iot|mqtt|网络|通信)',
    'BMS': r'(bms|电池|充电)',
    'Sensor': r'(sensor|传感器|加速度|陀螺仪)',
    'Display': r'(display|lcd|屏幕|仪表|显示)',
    'Storage': r'(storage|sd|eeprom|flash|存储)',
}


class CCodeParser:
    MODULE_PATTERNS = MODULE_PATTERNS

    def __init__(self, source_dir: str):
        self.source_dir = source_dir
        self.blocks: List[CodeBlock] = []

    def detect_module(self, file_path: str, content: str = "") -> str:
        file_path_lower = file_path.lower()
        content_lower = content.lower() if content else ""

        for module, pattern in self.MODULE_PATTERNS.items():
            if re.search(pattern, file_path_lower):
                return module
            if content_lower and re.search(pattern, content_lower):
                return module

        path_parts = file_path_lower.replace('\\', '/').split('/')
        for part in path_parts[-3:]:
            for module, pattern in self.MODULE_PATTERNS.items():
                if re.search(pattern, part):
                    return module

        return "General"

    def _build_context_prefix(self, file_path: str, file_name: str, module: str) -> str:
        module_marker = f"[{module}]" if module and module != "General" else ""
        return f"{module_marker} {file_name}"

    def _inject_context(self, block_content: str, file_path: str, file_name: str, module: str) -> str:
        prefix = self._build_context_prefix(file_path, file_name, module)
        return f"/* {prefix} */\n{block_content}"

    def parse_file(self, file_path: str) -> List[CodeBlock]:
        blocks = []
        encoding, content = EncodingConverter.convert_file(file_path)

        file_name = os.path.basename(file_path)
        module = self.detect_module(file_path, content)

        blocks.extend(self._extract_structs(content, file_path, file_name, module))
        blocks.extend(self._extract_enums(content, file_path, file_name, module))
        blocks.extend(self._extract_functions(content, file_path, file_name, module))
        blocks.extend(self._extract_macros(content, file_path, file_name, module))
        blocks.extend(self._extract_state_machines(content, file_path, file_name, module))

        self.blocks.extend(blocks)
        return blocks

    def _extract_structs(self, content: str, file_path: str, file_name: str, module: str) -> List[CodeBlock]:
        blocks = []
        struct_pattern = r'(?:typedef\s+)?struct\s*(\w*)\s*\{([^}]+)\}'
        for match in re.finditer(struct_pattern, content, re.MULTILINE | re.DOTALL):
            struct_name = match.group(1) or "anonymous_struct"
            struct_body = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            blocks.append(CodeBlock(
                file_path=file_path,
                type="struct",
                name=struct_name,
                content=self._inject_context(match.group(0), file_path, file_name, module),
                line_number=line_num,
                description=f"[{module}] {file_name} struct: {struct_name}",
                module=module
            ))
        return blocks

    def _extract_enums(self, content: str, file_path: str, file_name: str, module: str) -> List[CodeBlock]:
        blocks = []
        enum_pattern = r'(?:typedef\s+)?enum\s*(\w*)\s*\{([^}]+)\}'
        for match in re.finditer(enum_pattern, content, re.MULTILINE | re.DOTALL):
            enum_name = match.group(1) or "anonymous_enum"
            enum_body = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            blocks.append(CodeBlock(
                file_path=file_path,
                type="enum",
                name=enum_name,
                content=self._inject_context(match.group(0), file_path, file_name, module),
                line_number=line_num,
                description=f"[{module}] {file_name} enum: {enum_name}",
                module=module
            ))
        return blocks

    def _extract_functions(self, content: str, file_path: str, file_name: str, module: str) -> List[CodeBlock]:
        blocks = []
        func_pattern = r'((?:static\s+|extern\s+)?(?:\w+\s+)*?\w+\s+\*?\w+\s*\([^)]*\)\s*\{[^}]*\})'
        for match in re.finditer(func_pattern, content, re.MULTILINE | re.DOTALL):
            func_signature = match.group(1)[:200]
            line_num = content[:match.start()].count('\n') + 1
            func_name = re.search(r'(\w+)\s*\(', func_signature)
            if func_name:
                blocks.append(CodeBlock(
                    file_path=file_path,
                    type="function",
                    name=func_name.group(1),
                    content=self._inject_context(func_signature, file_path, file_name, module),
                    line_number=line_num,
                    description=f"[{module}] {file_name} function: {func_name.group(1)}",
                    module=module
                ))
        return blocks

    def _extract_macros(self, content: str, file_path: str, file_name: str, module: str) -> List[CodeBlock]:
        blocks = []
        macro_pattern = r'#define\s+(\w+)(?:\([^)]*\))?\s+(.+?)(?:\n|$)'
        for match in re.finditer(macro_pattern, content):
            macro_name = match.group(1)
            macro_body = match.group(2).strip()
            line_num = content[:match.start()].count('\n') + 1
            blocks.append(CodeBlock(
                file_path=file_path,
                type="macro",
                name=macro_name,
                content=self._inject_context(match.group(0), file_path, file_name, module),
                line_number=line_num,
                description=f"[{module}] {file_name} macro: {macro_name}",
                module=module
            ))
        return blocks

    def _extract_state_machines(self, content: str, file_path: str, file_name: str, module: str) -> List[CodeBlock]:
        blocks = []
        switch_pattern = r'switch\s*\(\s*(\w+)\s*\)\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
        for match in re.finditer(switch_pattern, content, re.MULTILINE | re.DOTALL):
            state_var = match.group(1)
            switch_body = match.group(2)
            line_num = content[:match.start()].count('\n') + 1
            blocks.append(CodeBlock(
                file_path=file_path,
                type="state_machine",
                name=f"state_machine_{state_var}",
                content=self._inject_context(match.group(0), file_path, file_name, module),
                line_number=line_num,
                description=f"[{module}] {file_name} state_machine: {state_var}",
                module=module
            ))
        return blocks

    def parse_directory(self) -> List[CodeBlock]:
        all_blocks = []
        for root, dirs, files in os.walk(self.source_dir):
            for file in files:
                if file.endswith(('.c', '.h')):
                    file_path = os.path.join(root, file)
                    try:
                        blocks = self.parse_file(file_path)
                        all_blocks.extend(blocks)
                    except Exception as e:
                        print(f"Error parsing {file_path}: {e}")
        self.blocks = all_blocks
        return all_blocks

    def get_blocks_by_type(self, block_type: str) -> List[CodeBlock]:
        return [b for b in self.blocks if b.type == block_type]

    def get_protocol_related_blocks(self) -> List[CodeBlock]:
        keywords = ['protocol', 'frame', 'packet', 'cmd', 'event', 'dp_', 'data_point', 'payload', 'ble', 'bluetooth', 'can', 'mqtt']
        return [b for b in self.blocks if any(k in b.content.lower() for k in keywords)]

    def export_to_dict(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": f"{block.file_path}:{block.line_number}:{block.type}:{block.name}",
                "type": block.type,
                "name": block.name,
                "content": block.content,
                "file_path": block.file_path,
                "line_number": block.line_number,
                "description": block.description,
                "module": block.module,
                "source": "c_code"
            }
            for block in self.blocks
        ]