import os
import re
import base64
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from .tool_executor import ToolExecutor, ToolResult
from .utils.text_cleaner import TextCleaner, QualityChecker
from .utils.chunker import SmartChunker


@dataclass
class ProtocolBlock:
    name: str
    type: str
    content: str
    scene: str
    source: str


class ProtocolDocParser:
    def __init__(self, source_dir: str, use_vision_fallback: bool = False):
        self.source_dir = source_dir
        self.blocks: List[ProtocolBlock] = []
        self.tool_executor = ToolExecutor()
        self.text_cleaner = TextCleaner()
        self.chunker = SmartChunker(min_chunk_size=200, max_chunk_size=1200)
        self.quality_checker = QualityChecker()
        self.use_vision_fallback = use_vision_fallback
        self._image_counter = 0

    def parse_file(self, file_path: str) -> List[ProtocolBlock]:
        blocks = []
        result = self.tool_executor.execute(file_path)

        if not result.success:
            print(f"Error parsing {file_path}: {result.error}")
            return blocks

        ext = os.path.splitext(file_path)[1].lower()

        if ext in ['.xlsx', '.xls']:
            blocks.extend(self._process_excel(result.data, file_path))
        elif isinstance(result.data, str):
            cleaned_text = self.text_cleaner.clean(result.data)
            blocks.extend(self._extract_blocks(cleaned_text, file_path, "text"))
        elif isinstance(result.data, list):
            page_data = [p for p in result.data if isinstance(p, dict)]
            pages_with_text = [p for p in page_data if p.get('text')]
            full_text = '\n'.join(p.get('text', '') for p in pages_with_text)

            if ext == '.pdf' and page_data:
                table_blocks = self._process_tables_with_coords(page_data, file_path)
                if table_blocks:
                    blocks.extend(table_blocks)

            if ext == '.pdf' and page_data:
                image_blocks = self._process_images(page_data, file_path)
                if image_blocks:
                    blocks.extend(image_blocks)

            if full_text:
                cleaned_text = self.text_cleaner.clean(full_text)
                blocks.extend(self._extract_blocks(cleaned_text, file_path, "document"))

        elif isinstance(result.data, list) and len(result.data) > 0:
            first_item = result.data[0]
            if isinstance(first_item, dict) and 'text' in first_item:
                full_text = '\n'.join(p.get('text', '') for p in result.data if isinstance(p, dict))
                cleaned_text = self.text_cleaner.clean(full_text)
                blocks.extend(self._extract_blocks(cleaned_text, file_path, "document"))

        processed_blocks = self._post_process_blocks(self._merge_short_blocks(blocks))
        self.blocks.extend(processed_blocks)
        return processed_blocks

    def _needs_vision(self, content: str) -> bool:
        return False

    def _fix_garbled_text_with_llm(self, text: str, context: str = "") -> str:
        try:
            import requests
            from config import MINIMAX_API_KEY

            prompt = f"""这是一段从PDF提取的技术文档文本，可能包含乱码字符（特别是CJK Radicals字符，如⼀、⽕、⽊等）。

请根据上下文修正乱码字符，将其替换为正确的中文或技术术语。

原始文本：
{text}

{context if context else "（无额外上下文）"}

请直接输出修正后的文本，不要解释。"""

            url = "https://api.minimax.chat/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": "MiniMax-M2.7",
                "max_tokens": 2000,
                "temperature": 0.3,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }

            session = requests.Session()
            session.trust_env = False

            response = session.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            result = response.json()

            if 'choices' in result and len(result['choices']) > 0:
                fixed = result['choices'][0]['message']['content']
                fixed = re.sub(r'<think>[\s\S]*?</think>', '', fixed)
                fixed = re.sub(r'<think>[\s\S]*?</think>', '', fixed)
                return fixed.strip()
        except Exception as e:
            print(f"LLM fix error: {e}")
        return text

    def _process_excel(self, data: Dict[str, List], file_path: str) -> List[ProtocolBlock]:
        blocks = []
        for sheet_name, rows in data.items():
            if rows:
                content = '\n'.join('\t'.join(str(cell) for cell in row) for row in rows)
                cleaned_content = self.text_cleaner.clean(content)
                blocks.append(ProtocolBlock(
                    name=f"Sheet: {sheet_name}",
                    type="excel_table",
                    content=cleaned_content,
                    scene="",
                    source=file_path
                ))
        return blocks

    def _process_tables(self, pages: List[Dict], file_path: str) -> List[ProtocolBlock]:
        blocks = []
        table_counter = 0
        for page in pages:
            if isinstance(page, dict):
                tables = page.get('tables', [])
                page_text = page.get('text', '')

                if tables and len(tables) > 0:
                    for table in tables:
                        if table and len(table) > 0:
                            table_text = self._table_to_text(table)
                            if table_text:
                                cleaned_text = self.text_cleaner.clean(table_text)
                                if len(cleaned_text.strip()) >= 10:
                                    blocks.append(ProtocolBlock(
                                        name=f"Table_{table_counter + 1}",
                                        type="table",
                                        content=cleaned_text,
                                        scene="",
                                        source=file_path
                                    ))
                                    table_counter += 1
                elif page_text and len(page_text.strip()) >= 10:
                    cleaned_text = self.text_cleaner.clean(page_text)
                    blocks.append(ProtocolBlock(
                        name=f"Table_{table_counter + 1}",
                        type="text_fallback",
                        content=cleaned_text,
                        scene="table_fallback",
                        source=file_path
                    ))
                    table_counter += 1
        return blocks

    def _process_images(self, pages: List[Dict], file_path: str) -> List[ProtocolBlock]:
        blocks = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            images = page.get('images', [])
            if not images:
                continue
            page_num = page.get('page', 0)
            page_text = page.get('text', '')
            for img_info in images:
                img_path = img_info.get('path', '')
                if not img_path or not os.path.exists(img_path):
                    continue
                self._image_counter += 1
                scene = self._extract_scene(page_text) if page_text else ""
                img_size = ""
                if img_info.get('width') and img_info.get('height'):
                    img_size = f"尺寸{img_info['width']}x{img_info['height']}"
                nearby_text = self._get_nearby_text(page, img_info)

                is_table, table_markdown = self._classify_image_with_vision(img_path, page_text)

                if is_table and table_markdown:
                    blocks.append(ProtocolBlock(
                        name=f"Table_Image_{self._image_counter}",
                        type="table_image",
                        content=table_markdown,
                        scene=scene,
                        source=file_path
                    ))
                else:
                    blocks.append(ProtocolBlock(
                        name=f"Image_{self._image_counter}",
                        type="image",
                        content=f"[图片文件: {img_path}]\n[来源: PDF page {page_num}]\n[{img_size}]\n[上下文] {nearby_text}",
                        scene=scene,
                        source=file_path
                    ))
        return blocks

    def _classify_image_with_vision(self, img_path: str, context: str = "") -> tuple:
        # Skip vision API if already processed many images (performance optimization)
        if self._image_counter >= 10:
            return False, ""

        try:
            import requests
            from config import MINIMAX_API_KEY

            with open(img_path, 'rb') as f:
                img_base64 = base64.b64encode(f.read()).decode('utf-8')

            prompt = """请判断这张图片的内容类型：
1. 如果图片是表格（含框表格、无线表格、合并单元格表格等），请用Markdown格式输出表格内容
2. 如果图片是流程图、示意图、框图、截图等其他内容，请直接输出"NOT_TABLE"

回答格式：
- 如果是表格：直接输出Markdown表格，不要其他内容
- 如果不是表格：直接输出"NOT_TABLE"，不要其他内容"""

            if context:
                prompt = f"图片上下文：{context[:200]}\n\n{prompt}"

            url = "https://api.minimax.chat/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {MINIMAX_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "MiniMax-M2.7",
                "max_tokens": 2000,
                "temperature": 0.3,
                "messages": [
                    {"role": "user", "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}},
                        {"type": "text", "text": prompt}
                    ]}
                ]
            }

            session = requests.Session()
            session.trust_env = False
            response = session.post(url, headers=headers, json=payload, timeout=30)

            if response.status_code == 200:
                result = response.json()
                if result.get('choices') and result['choices'][0].get('message', {}).get('content'):
                    content = result['choices'][0]['message']['content'].strip()
                    if content == "NOT_TABLE":
                        return False, ""
                    if content.startswith('|') or content.startswith('\\|'):
                        return True, content
            return False, ""
        except Exception as e:
            print(f"Vision classify error: {e}")
            return False, ""

    def _get_nearby_text(self, page: Dict, img_info: Dict) -> str:
        page_text = page.get('text', '')
        if not page_text:
            return ""
        lines = page_text.split('\n')
        nearby_lines = []
        for line in lines:
            if line.strip():
                nearby_lines.append(line.strip())
        return ' '.join(nearby_lines[:5])[:200]

    def _merge_short_blocks(self, blocks: List[ProtocolBlock], min_content_len: int = 30) -> List[ProtocolBlock]:
        if not blocks:
            return blocks

        merged = []
        for block in blocks:
            if len(block.content.strip()) < min_content_len:
                if merged and block.type != 'table':
                    merged[-1].content += "\n" + block.content
                    continue
            merged.append(block)

        return merged

    def _process_tables_with_coords(self, pages: List[Dict], file_path: str) -> List[ProtocolBlock]:
        blocks = []
        table_counter = 0
        for page in pages:
            if not isinstance(page, dict):
                continue

            page_num = page.get('page', 0)
            tables = page.get('tables', [])

            if not tables:
                coord_table = self._reconstruct_table_from_coords(page, page_num)
                if coord_table:
                    blocks.append(ProtocolBlock(
                        name=f"Table_{table_counter + 1}",
                        type="table",
                        content=coord_table,
                        scene="",
                        source=file_path
                    ))
                    table_counter += 1
            else:
                for table in tables:
                    if table and len(table) > 0:
                        if not self._is_valid_table(table):
                            continue
                        table_text = self._table_to_text(table)
                        if table_text:
                            blocks.append(ProtocolBlock(
                                name=f"Table_{table_counter + 1}",
                                type="table",
                                content=table_text,
                                scene="",
                                source=file_path
                            ))
                            table_counter += 1

        return blocks

    def _reconstruct_table_from_coords(self, page: Dict, page_num: int) -> str:
        try:
            import pdfplumber
            pdf_path = page.get('source', '')
            if not pdf_path:
                return ""

            with pdfplumber.open(pdf_path) as pdf:
                if page_num > len(pdf.pages):
                    return ""
                page_obj = pdf.pages[page_num - 1]
                words = page_obj.extract_words()

                if not words or len(words) < 5:
                    return ""

                col_threshold = 10
                row_threshold = 15

                x_positions = sorted(set(int(w['x0']) for w in words))
                col_boundaries = []
                for i in range(len(x_positions) - 1):
                    if x_positions[i+1] - x_positions[i] > col_threshold:
                        col_boundaries.append((x_positions[i] + x_positions[i+1]) / 2)

                y_positions = sorted(set(int(w['top']) for w in words))
                row_boundaries = []
                for i in range(len(y_positions) - 1):
                    if y_positions[i+1] - y_positions[i] > row_threshold:
                        row_boundaries.append((y_positions[i] + y_positions[i+1]) / 2)

                def get_col(text_x):
                    col = 0
                    for boundary in sorted(col_boundaries):
                        if text_x < boundary:
                            break
                        col += 1
                    return col

                def get_row(text_y):
                    row = 0
                    for boundary in sorted(row_boundaries):
                        if text_y < boundary:
                            break
                        row += 1
                    return row

                grid = {}
                for w in words:
                    row = get_row(w['top'])
                    col = get_col(w['x0'])
                    key = (row, col)
                    if key not in grid:
                        grid[key] = []
                    grid[key].append(w['text'])

                if not grid:
                    return ""

                max_row = max(r for r, c in grid.keys())
                max_col = max(c for r, c in grid.keys())

                if max_col < 1:
                    return ""

                rows = []
                for r in range(max_row + 1):
                    row_cells = []
                    for c in range(max_col + 1):
                        cell_texts = grid.get((r, c), [])
                        cell_text = ' '.join(sorted(cell_texts, key=lambda x: next((words.index(w) for w in words if w['text'] == x), 0)))
                        row_cells.append(cell_text.strip())
                    rows.append(row_cells)

                if len(rows) < 2:
                    return ""

                if not self._is_valid_table(rows):
                    return ""

                return self._table_to_text(rows)

        except Exception as e:
            return ""

    def _is_valid_table(self, rows: List[List[str]]) -> bool:
        if len(rows) < 2:
            return False

        non_empty_rows = [r for r in rows if any(c.strip() for c in r)]
        if len(non_empty_rows) < 2:
            return False

        col_counts = [len([c for c in r if c.strip()]) for r in rows]
        if not col_counts:
            return False

        avg_cols = sum(col_counts) / len(col_counts)
        if avg_cols < 1.5:
            return False

        for count in col_counts:
            if count > 0 and abs(count - avg_cols) > avg_cols * 0.5:
                return False

        header_row = rows[0]
        header_non_empty = [c for c in header_row if c.strip()]
        if len(header_non_empty) < 2:
            return False

        return True

    def _table_to_text(self, table: List[List]) -> str:
        if not table or len(table) < 2:
            return self._table_to_tab_separated(table)

        min_cols = min(len(row) for row in table if row)
        if min_cols < 2:
            return self._table_to_tab_separated(table)

        col_widths = []
        for i in range(min_cols):
            max_width = 0
            for row in table:
                if i < len(row) and row[i]:
                    cell_len = len(str(row[i]).strip())
                    max_width = max(max_width, cell_len)
            col_widths.append(min(max_width, 30))

        lines = []
        header = table[0]
        header_cells = []
        for i, cell in enumerate(header):
            if i >= min_cols:
                break
            cell_text = str(cell).strip() if cell else ''
            width = col_widths[i]
            header_cells.append(f" {cell_text:<{width}} ")
        lines.append('| ' + ' | '.join(header_cells) + ' |')

        sep_cells = []
        for width in col_widths[:min_cols]:
            sep_cells.append('-' * (width + 2))
        lines.append('|' + '|'.join(sep_cells) + '|')

        for row in table[1:]:
            row_cells = []
            for i in range(min_cols):
                cell_text = str(row[i]).strip() if i < len(row) and row[i] else ''
                if len(cell_text) > col_widths[i]:
                    cell_text = cell_text[:col_widths[i]-3] + '...'
                row_cells.append(f" {cell_text:<{col_widths[i]}} ")
            lines.append('| ' + ' | '.join(row_cells) + ' |')

        return '\n'.join(lines)

    def _table_to_tab_separated(self, table: List[List]) -> str:
        if not table:
            return ''
        lines = []
        for row in table:
            cell_str = '\t'.join(str(cell).strip() if cell else '' for cell in row)
            if cell_str.strip():
                lines.append(cell_str)
        return '\n'.join(lines)

    def _extract_blocks(self, text: str, file_path: str, source_type: str) -> List[ProtocolBlock]:
        blocks = []

        cmd_pattern = r'(?:命令|指令|CMD|cmd|帧ID|Frame.?ID|Message.?ID)\s*[:：]?\s*(0x[0-9A-Fa-f]+|[A-Fa-f0-9]{2,4}|[A-Z_]+)'
        for match in re.finditer(cmd_pattern, text):
            cmd_id = match.group(1)
            context = text[max(0, match.start()-200):min(len(text), match.end()+200)]
            if len(context) > 50:
                scene = self._extract_scene(context)
                blocks.append(ProtocolBlock(
                    name=f"CMD: {cmd_id}",
                    type="command",
                    content=context,
                    scene=scene,
                    source=file_path
                ))

        smart_chunks = self.chunker.chunk_document(text, preserve_structure=True)
        for i, chunk in enumerate(smart_chunks[:30]):
            if len(chunk['content']) > 80:
                chunk_type = chunk['type']
                if any(b.type == 'command' and chunk['content'][:200] in b.content for b in blocks):
                    continue
                scene = self._extract_scene(chunk['content'])
                blocks.append(ProtocolBlock(
                    name=chunk['title'] or f"Section_{i+1}",
                    type=chunk_type,
                    content=chunk['content'],
                    scene=scene,
                    source=file_path
                ))

        return blocks

    def _extract_scene(self, text: str) -> str:
        scene_keywords = ['场景', '使用', '触发', '条件', '何时', '什么情况下', '适用']
        for keyword in scene_keywords:
            if keyword in text:
                idx = text.index(keyword)
                return text[idx:idx+100]
        return ""

    def _generate_block_name(self, block: ProtocolBlock, all_blocks: List[ProtocolBlock]) -> str:
        content = block.content.strip()
        if not content:
            return block.name

        lines = content.split('\n')
        meaningful_lines = [l for l in lines if len(l.strip()) > 5][:5]

        if block.type == 'table':
            header_match = re.search(r'^[\u4e00-\u9fa5A-Za-z]+', content)
            if header_match:
                return header_match.group(0)[:30]
            return f"表格_{len(all_blocks) + 1}"

        if block.type == 'command':
            cmd_match = re.search(r'0x[0-9A-Fa-f]+', content)
            if cmd_match:
                return f"命令_{cmd_match.group(0)}"
            return block.name

        for line in meaningful_lines:
            heading, level = self.chunker.detect_heading(line)
            if heading and level >= 0:
                clean_heading = re.sub(r'^[第\d一二三四五六七八九十百千]+[章节部分篇节]?\s*', '', heading)
                if 4 <= len(clean_heading) <= 30:
                    return clean_heading[:40]

        for line in meaningful_lines:
            if len(line.strip()) >= 5:
                heading_match = re.match(r'^(第?[一二三四五六七八九十百千\d]+[、.．:：])\s*', line.strip())
                if heading_match:
                    title_part = line.strip()[heading_match.end():]
                    if 4 <= len(title_part) <= 25:
                        return title_part[:25]

        first_line = meaningful_lines[0] if meaningful_lines else content[:30]
        clean_first = re.sub(r'^[【\[]?\s*', '', first_line[:30])
        return clean_first if 4 <= len(clean_first) <= 25 else block.name

    def _is_incomplete_block_name(self, name: str) -> bool:
        incomplete_patterns = [
            r'^Section_\d+$',
            r'^Table_\d+$',
            r'^表格_\d+$',
            r'^第?\d*[章节部分篇节]?$',
        ]
        for pattern in incomplete_patterns:
            if re.match(pattern, name):
                return True
        if len(name) < 4 or len(name) > 30:
            return True

    def _find_contextual_title(self, block: ProtocolBlock, preceding_blocks: List[ProtocolBlock]) -> Optional[str]:
        search_blocks = preceding_blocks[-5:] if len(preceding_blocks) >= 5 else preceding_blocks

        for prev in reversed(search_blocks):
            if prev.type in ['chapter', 'section'] and not self._is_incomplete_block_name(prev.name):
                return prev.name

        content_lines = block.content.split('\n')
        for line in content_lines[:10]:
            heading, level = self.chunker.detect_heading(line)
            if heading and level <= 1:
                return heading[:40]

        return None

    def _compute_text_hash(self, text: str, window_size: int = 50) -> str:
        import hashlib
        text = re.sub(r'\s+', ' ', text.strip().lower())
        if len(text) <= window_size:
            return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]
        shingles = [text[i:i+window_size] for i in range(len(text) - window_size + 1)]
        minhash = min(hashlib.md5(s.encode('utf-8')).hexdigest()[:8] for s in shingles)
        return minhash

    def _edit_distance_ratio(self, s1: str, s2: str) -> float:
        if not s1 or not s2:
            return 0.0
        s1, s2 = s1.lower(), s2.lower()
        if s1 == s2:
            return 1.0
        len1, len2 = len(s1), len(s2)
        if abs(len1 - len2) > max(len1, len2) * 0.5:
            return 0.0
        d = [[0] * (len2 + 1) for _ in range(len1 + 1)]
        for i in range(len1 + 1):
            d[i][0] = i
        for j in range(len2 + 1):
            d[0][j] = j
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if s1[i-1] == s2[j-1] else 1
                d[i][j] = min(d[i-1][j] + 1, d[i][j-1] + 1, d[i-1][j-1] + cost)
        distance = d[len1][len2]
        return 1.0 - (distance / max(len1, len2))

    def _deduplicate_blocks(self, blocks: List[ProtocolBlock], similarity_threshold: float = 0.8) -> List[ProtocolBlock]:
        if not blocks:
            return blocks
        unique_blocks = []
        for block in blocks:
            is_duplicate = False
            for existing in unique_blocks:
                hash_sim = 1.0 if self._compute_text_hash(block.content) == self._compute_text_hash(existing.content) else 0.0
                content_sim = self._edit_distance_ratio(block.content[:500], existing.content[:500])
                combined_sim = max(hash_sim, content_sim)
                if combined_sim >= similarity_threshold:
                    if existing.type == 'command' and block.type != 'command':
                        is_duplicate = True
                        break
                    if len(block.content) > len(existing.content):
                        existing.content = block.content
                        existing.name = block.name
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_blocks.append(block)
        return unique_blocks

    def _post_process_blocks(self, blocks: List[ProtocolBlock]) -> List[ProtocolBlock]:
        blocks = self._deduplicate_blocks(blocks, similarity_threshold=0.8)

        for i, block in enumerate(blocks):
            if self._is_incomplete_block_name(block.name):
                contextual = self._find_contextual_title(block, blocks[:i])
                if contextual:
                    contextual_truncated = contextual[:20] + "..." if len(contextual) > 20 else contextual
                    block.name = f"{contextual_truncated} -> {block.name}"
                else:
                    block.name = self._generate_block_name(block, blocks[:i])

            block.content = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', block.content)
            block.content = re.sub(r'\n{3,}', '\n\n', block.content)
            block.name = re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', block.name)

            quality_result = self.quality_checker.check_quality(block.content)
            needs_fix = quality_result.garbage_ratio > 0.05

            if not needs_fix:
                cjk_radical_pattern = re.compile(r'[\u2f00-\u2fdf\u2e80-\u2eff]')
                if cjk_radical_pattern.search(block.content):
                    needs_fix = True

            if needs_fix:
                context_blocks = [b.content[:200] for b in blocks[:i+1] if b != block]
                context = "\n".join(context_blocks[-3:]) if context_blocks else ""
                block.content = self._fix_garbled_text_with_llm(block.content, context)

        return blocks

    def export_to_dict(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": f"{b.source}:{i}",
                "type": b.type,
                "name": b.name,
                "content": b.content,
                "source": b.source,
                "scene": b.scene
            }
            for i, b in enumerate(self.blocks)
        ]

    def parse_directory(self) -> List[Dict[str, Any]]:
        all_blocks = []
        valid_exts = {'.pdf', '.docx', '.doc', '.xlsx', '.xls', '.txt', '.md'}
        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if 'paddleocr' not in d.lower() and 'output' not in d.lower()]
            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in valid_exts:
                    file_path = os.path.join(root, file)
                    try:
                        result = self.tool_executor.execute(file_path)
                        if not result.success:
                            print(f"Error parsing {file_path}: {result.error}")
                            continue

                        file_basename = os.path.basename(file_path)
                        blocks = []

                        # PaddleOCR/EnhancedPDFParser format: list of dicts with id/type/title/content
                        if isinstance(result.data, list) and result.data:
                            first = result.data[0]
                            if isinstance(first, dict) and 'id' in first and 'content' in first:
                                # Direct block format from EnhancedPDFParser
                                for item in result.data:
                                    raw_content = item.get('content', '')
                                    cleaned_content = self.text_cleaner.clean(raw_content)
                                    blocks.append(ProtocolBlock(
                                        name=item.get('title', item.get('name', 'Untitled')),
                                        type=item.get('type', 'protocol_doc'),
                                        content=cleaned_content,
                                        scene=item.get('scene', ''),
                                        source=file_path
                                    ))
                                self.blocks.extend(blocks)
                            elif isinstance(first, dict) and 'text' in first:
                                # Page format from _parse_md or _parse_pdf (pdfplumber)
                                for i, page in enumerate(result.data):
                                    if isinstance(page, dict) and page.get('text'):
                                        cleaned = self.text_cleaner.clean(page.get('text', ''))
                                        section_blocks = self._extract_blocks(cleaned, file_path, "document")
                                        blocks.extend(section_blocks)
                                self.blocks.extend(blocks)
                        elif isinstance(result.data, str):
                            cleaned = self.text_cleaner.clean(result.data)
                            section_blocks = self._extract_blocks(cleaned, file_path, "text")
                            blocks.extend(section_blocks)
                            self.blocks.extend(blocks)

                        all_blocks.extend([
                            {
                                "id": f"{file_path}:{i}",
                                "type": b.type,
                                "name": b.name,
                                "content": b.content,
                                "source": b.source,
                                "scene": b.scene
                            }
                            for i, b in enumerate(blocks)
                        ])
                        print(f"Parsed {file_basename}: {len(blocks)} blocks")
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")
        return all_blocks
