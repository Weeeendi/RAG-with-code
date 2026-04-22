import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .text_cleaner import ListAwareMerger


@dataclass
class Chunk:
    title: str
    content: str
    chunk_type: str
    level: int
    start_line: int
    end_line: int
    parent_title: Optional[str] = None
    heading_path: Optional[str] = None


class SmartChunker:
    HEADING_PATTERNS = [
        (r'^第[一二三四五六七八九十百千]+[章节部分篇]', 0),
        (r'^[一二三四五六七八九十百千]+[、.．]', 0),
        (r'^\d+[.．、]\s*[\u4e00-\u9fa5]', 1),
        (r'^\d+[\u4e00-\u9fa5]{2,}', 1),
        (r'^\d+\.\d+\s*', 2),
        (r'^[A-Z][.．]\s*', 1),
        (r'^[A-Z]\.\d+\s*', 2),
        (r'^#{1,6}\s*', 0),
        (r'^[一二三四五六七八九十]+、\s*', 0),
        (r'^\d+、\s*[\u4e00-\u9fa5]', 1),
        (r'^\d+\.\s*[\u4e00-\u9fa5]', 1),
        (r'^\[\d+\]\s*', 1),
        (r'^\(\d+\)\s*', 1),
    ]

    LIST_PATTERNS = [
        r'^[\•\◦\-\*\+]\s*',
        r'^\d+[.．)）]\s*',
        r'^[(（]\d+[)）]\s*',
    ]

    SEMANTIC_BREAK_KEYWORDS = [
        '触发条件', '断连机制', '处理机制', '上报规则', '生成逻辑',
        '数据来源', '超时说明', '设计理由', '补充说明', '注意事项',
        '场景', '条件', '机制', '规则', '逻辑', '说明',
    ]

    TITLE_KEYWORDS = [
        '行程记录', '骑行记录', '数据来源', '超时', '断连', '上报规则',
        '生成逻辑', '触发条件', '处理机制', '设计理由', '补充说明'
    ]

    INCOMPLETE_TITLE_PREFIXES = [
        '程未', '连接蓝', '建立连', '数据参', '速度里', '骑行距',
        '超时结', '防止用', '确保每', '生成一', '备已', '备开机', '设备已'
    ]

    HEADING_MAX_LEN = 20

    def __init__(self, min_chunk_size: int = 100, max_chunk_size: int = 800, overlap_lines: int = 3):
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.overlap_lines = overlap_lines

    def is_incomplete_title(self, title: str, lines: List[str], current_idx: int) -> bool:
        if len(title) < 4:
            return True

        for prefix in self.INCOMPLETE_TITLE_PREFIXES:
            if title.startswith(prefix) or prefix in title:
                return True

        if len(title) > self.HEADING_MAX_LEN:
            return True

        heading_like_patterns = [
            r'^[\u4e00-\u9fa5]+[、:：]',
            r'^(第[一二三四五六七八九十百千]+[章节部分篇节]?)',
            r'^\d+[.．、]\s*[\u4e00-\u9fa5]',
        ]
        for pattern in heading_like_patterns:
            if re.match(pattern, title):
                return False

        return True

    def find_parent_section(self, lines: List[str], current_idx: int) -> Optional[str]:
        search_window = lines[max(0, current_idx-10):current_idx]

        for line in reversed(search_window):
            line_stripped = line.strip()
            if not line_stripped:
                continue

            heading, level = self.detect_heading(line_stripped)
            if heading and level <= 1:
                return heading[:20] if heading else None

            heading_start_patterns = [
                r'^[一二三四五六七八九十百千]+[、.]',
                r'^(第[一二三四五六七八九十百千]+[章节部分篇节]?)',
                r'^\d+[.．、]\s*[\u4e00-\u9fa5]',
            ]
            for pattern in heading_start_patterns:
                if re.match(pattern, line_stripped):
                    if len(line_stripped) > 5 and len(line_stripped) < 50:
                        return line_stripped[:40]

        return None

    def detect_heading(self, line: str) -> Tuple[Optional[str], int]:
        line_stripped = line.strip()
        if not line_stripped:
            return None, -1

        for pattern, level in self.HEADING_PATTERNS:
            match = re.match(pattern, line_stripped)
            if match:
                heading_text = line_stripped[match.end():].strip()
                if len(heading_text) > self.HEADING_MAX_LEN:
                    heading_text = heading_text[:self.HEADING_MAX_LEN]
                return heading_text, level

        return None, -1

    def is_list_item(self, line: str) -> bool:
        line_stripped = line.strip()
        for pattern in self.LIST_PATTERNS:
            if re.match(pattern, line_stripped):
                return True
        return False

    def _truncate_path_node(self, title: str, max_len: int = 20) -> str:
        if len(title) <= max_len:
            return title
        return title[:max_len] + "..."

    def is_semantic_break(self, line: str) -> bool:
        stripped = line.strip()
        for keyword in self.SEMANTIC_BREAK_KEYWORDS:
            if keyword in stripped and len(stripped) < 30:
                return True
        return False

    def split_into_sections(self, text: str) -> List[Dict[str, Any]]:
        lines = text.split('\n')
        sections = []
        current_section = {
            'heading': None,
            'level': 0,
            'lines': [],
            'start_line': 0
        }

        for i, line in enumerate(lines):
            heading, level = self.detect_heading(line)
            if heading is not None:
                if current_section['lines']:
                    sections.append(current_section)
                current_section = {
                    'heading': heading,
                    'level': level,
                    'lines': [line],
                    'start_line': i
                }
            else:
                current_section['lines'].append(line)

        if current_section['lines']:
            sections.append(current_section)

        return sections

    def merge_short_lines(self, lines: List[str]) -> List[str]:
        if not lines:
            return lines
        return ListAwareMerger.merge_lines(lines, min_line_len=20)

    def create_chunks(self, text: str, preserve_structure: bool = True) -> List[Chunk]:
        if not text:
            return []

        sections = self.split_into_sections(text)
        chunks = []

        heading_stack = []
        current_heading_path = ""
        all_lines = text.split('\n')

        for section in sections:
            heading = section['heading']
            level = section['level']
            raw_lines = section['lines']
            start_line = section['start_line']

            if heading is not None and self.is_incomplete_title(heading, all_lines, start_line):
                parent = self.find_parent_section(all_lines, start_line)
                if parent:
                    heading = parent
                    level = max(0, level - 1)

            while heading_stack and heading_stack[-1][1] >= level:
                heading_stack.pop()

            if heading is not None:
                heading_stack.append((heading, level))
                current_heading_path = " -> ".join([self._truncate_path_node(h[0]) for h in heading_stack])
            elif heading_stack:
                current_heading_path = " -> ".join([self._truncate_path_node(h[0]) for h in heading_stack])

            parent_title = heading_stack[-1][0] if heading_stack else None

            if preserve_structure:
                merged_lines = self.merge_short_lines(raw_lines)
            else:
                merged_lines = [l.strip() for l in raw_lines if l.strip()]

            section_text = '\n'.join(merged_lines)
            section_len = len(section_text)

            if section_len < self.min_chunk_size and heading is None:
                if chunks and chunks[-1].end_line >= start_line - 2:
                    chunks[-1].content += '\n' + section_text
                    chunks[-1].end_line = start_line + len(raw_lines)
                    continue
                chunks.append(Chunk(
                    title=f"Section_{start_line}",
                    content=section_text,
                    chunk_type="document_section",
                    level=level,
                    start_line=start_line,
                    end_line=start_line + len(raw_lines),
                    parent_title=parent_title,
                    heading_path=current_heading_path
                ))
                continue

            if section_len <= self.max_chunk_size:
                chunk_type = "section"
                if level == 0:
                    chunk_type = "chapter"
                elif level == 1:
                    chunk_type = "section"
                elif self.is_list_item('\n'.join(merged_lines[:3])):
                    chunk_type = "list"

                chunks.append(Chunk(
                    title=heading or f"Section_{start_line}",
                    content=section_text,
                    chunk_type=chunk_type,
                    level=level,
                    start_line=start_line,
                    end_line=start_line + len(raw_lines),
                    parent_title=parent_title,
                    heading_path=current_heading_path
                ))
            else:
                sub_chunks = self.split_large_section(section_text, merged_lines, start_line, heading, parent_title, current_heading_path)
                chunks.extend(sub_chunks)

        return chunks

    def split_large_section(self, section_text: str, lines: List[str], start_line: int, heading: Optional[str],
                          parent_title: Optional[str] = None, heading_path: str = "") -> List[Chunk]:
        sub_chunks = []
        current_lines = []
        current_size = 0

        for i, line in enumerate(lines):
            line_len = len(line)
            if current_size + line_len > self.max_chunk_size and current_lines:
                sub_content = '\n'.join(current_lines)
                if heading:
                    title = heading
                else:
                    title = f"Line_{start_line + i}"

                sub_chunks.append(Chunk(
                    title=title,
                    content=sub_content,
                    chunk_type="subsection",
                    level=1,
                    start_line=start_line + i - len(current_lines),
                    end_line=start_line + i,
                    parent_title=parent_title,
                    heading_path=heading_path
                ))

                overlap_start = max(0, len(current_lines) - self.overlap_lines)
                current_lines = current_lines[overlap_start:]
                current_size = sum(len(l) for l in current_lines)

            current_lines.append(line)
            current_size += line_len

        if current_lines:
            sub_content = '\n'.join(current_lines)
            sub_chunks.append(Chunk(
                title=heading or f"Line_{start_line}",
                content=sub_content,
                chunk_type="subsection",
                level=1,
                start_line=start_line + len(lines) - len(current_lines),
                end_line=start_line + len(lines),
                parent_title=parent_title,
                heading_path=heading_path
            ))

        return sub_chunks

    def chunk_document(self, text: str, preserve_structure: bool = True, inject_heading: bool = True) -> List[Dict[str, Any]]:
        chunks = self.create_chunks(text, preserve_structure)
        result = []
        for chunk in chunks:
            content = chunk.content
            if inject_heading and chunk.heading_path and chunk.parent_title != chunk.title:
                content = f"【{chunk.heading_path}】\n{content}"

            result.append({
                'title': chunk.title,
                'content': content,
                'type': chunk.chunk_type,
                'level': chunk.level,
                'start_line': chunk.start_line,
                'end_line': chunk.end_line,
                'parent_title': chunk.parent_title,
                'heading_path': chunk.heading_path
            })
        return result


def smart_chunk(text: str, min_size: int = 100, max_size: int = 800) -> List[Dict[str, Any]]:
    chunker = SmartChunker(min_chunk_size=min_size, max_chunk_size=max_size)
    return chunker.chunk_document(text)