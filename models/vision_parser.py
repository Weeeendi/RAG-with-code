import os
import io
import base64
import re
import subprocess
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class VisionParseResult:
    page_num: int
    markdown: str
    quality_score: float
    table_structures: List[List[List[str]]]
    error: Optional[str] = None


class MarkerParser:
    def __init__(self):
        self.marker_available = self._check_marker()

    def _check_marker(self) -> bool:
        try:
            result = subprocess.run(
                ['marker', '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except:
            return False

    def convert_pdf_to_markdown(self, pdf_path: str, output_dir: str = None) -> Optional[str]:
        if not self.marker_available:
            return None

        try:
            if output_dir is None:
                output_dir = os.path.dirname(pdf_path)

            result = subprocess.run(
                ['marker', pdf_path, '--output_dir', output_dir],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode == 0:
                md_path = os.path.splitext(pdf_path)[0] + '.md'
                if os.path.exists(md_path):
                    with open(md_path, 'r', encoding='utf-8') as f:
                        return f.read()
        except Exception as e:
            pass

        return None

    def convert_page_to_markdown(self, pdf_path: str, page_num: int) -> Optional[str]:
        full_markdown = self.convert_pdf_to_markdown(pdf_path)
        if full_markdown is None:
            return None

        pages = full_markdown.split('--- Page ')
        for page in pages:
            if page.startswith(str(page_num)):
                parts = page.split('---', 1)
                if len(parts) > 1:
                    return parts[1].strip()
        return None


class VisionGateKeeper:
    GARBAGE_THRESHOLD = 0.07
    SUSPICIOUS_CHARS = ['\uf0a0', '\uf020', '\xa0', '\x00', '\u3000']
    UNKNOWN_CHAR_THRESHOLD = 0.02

    def __init__(self, min_confidence: float = 0.7):
        self.min_confidence = min_confidence

    def needs_vision_parsing(self, text: str, garbage_ratio: float) -> bool:
        if garbage_ratio > self.GARBAGE_THRESHOLD:
            return True

        chinese_chars = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
        total_chars = len(text) if len(text) > 0 else 1
        chinese_ratio = chinese_chars / total_chars

        if chinese_ratio < 0.05:
            return True

        for pattern in self.SUSPICIOUS_CHARS:
            if pattern in text:
                return True

        if self._has_unknown_chars(text):
            return True

        return False

    def _has_unknown_chars(self, text: str) -> bool:
        unknown_count = 0
        for char in text:
            code = ord(char)
            if 0x3400 <= code <= 0x4DBF:
                unknown_count += 1
        return unknown_count / len(text) > self.UNKNOWN_CHAR_THRESHOLD if len(text) > 0 else False

    def should_use_vision(self, blocks: List[Dict]) -> Tuple[bool, List[int]]:
        vision_needed_pages = []
        for i, block in enumerate(blocks):
            content = block.get('content', '')
            garbage = block.get('garbage_ratio', 0)
            if self.needs_vision_parsing(content, garbage):
                vision_needed_pages.append(i)
        return len(vision_needed_pages) > 0, vision_needed_pages

    def extract_suspicious_words(self, text: str) -> List[str]:
        suspicious = []
        words = re.findall(r'[\u4e00-\u9fff]+', text)
        for word in words:
            if len(word) == 1:
                continue
            has_unknown = any(0x3400 <= ord(c) <= 0x4DBF for c in word)
            if has_unknown:
                suspicious.append(word)
        return suspicious


class VisionDocumentParser:
    def __init__(self, api_key: str = None):
        from config import MINIMAX_API_KEY, PROXIES
        self.api_key = api_key or MINIMAX_API_KEY
        self.proxies = PROXIES
        self.gatekeeper = VisionGateKeeper()
        self.marker = MarkerParser()

    def _render_pdf_page_to_image(self, pdf_path: str, page_num: int, dpi: int = 150) -> bytes:
        try:
            import fitz
            doc = fitz.open(pdf_path)
            page = doc[page_num - 1]
            mat = fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)
            img_data = pix.tobytes("png")
            doc.close()
            return img_data
        except Exception as e:
            raise RuntimeError(f"Failed to render PDF page {page_num}: {e}")

    def _call_vision_api(self, image_base64: str, original_text: str, context: str = "") -> str:
        import requests

        prompt = f"""请逐字识别这张图片中的所有文字内容。
如果图片中有表格，请用Markdown表格格式输出。
请保留所有技术术语（0x8005、0x0003、DP、OTA、BLE等）。
直接输出识别结果，不需要解释。"""

        url = "https://api.minimax.chat/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": "MiniMax-M2.7",
            "max_tokens": 3000,
            "temperature": 0.3,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        },
                        {
                            "type": "text",
                            "text": prompt
                        }
                    ]
                }
            ]
        }

        session = requests.Session()
        session.trust_env = False

        response = session.post(url, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json()

        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        return original_text

    def parse_page_with_marker(self, pdf_path: str, page_num: int) -> VisionParseResult:
        try:
            markdown = self.marker.convert_page_to_markdown(pdf_path, page_num)
            if markdown:
                return VisionParseResult(
                    page_num=page_num,
                    markdown=markdown,
                    quality_score=0.95,
                    table_structures=self._extract_tables_from_markdown(markdown)
                )
        except Exception as e:
            pass

        return VisionParseResult(
            page_num=page_num,
            markdown="",
            quality_score=0.0,
            table_structures=[],
            error="Marker conversion failed"
        )

    def correct_page(self, pdf_path: str, page_num: int, original_text: str, context: str = "") -> VisionParseResult:
        try:
            img_bytes = self._render_pdf_page_to_image(pdf_path, page_num, dpi=150)
            img_base64 = base64.b64encode(img_bytes).decode('utf-8')

            markdown = self._call_vision_api(img_base64, original_text, context)
            markdown = self._strip_thinking_tags(markdown)

            return VisionParseResult(
                page_num=page_num,
                markdown=markdown,
                quality_score=0.95,
                table_structures=self._extract_tables_from_markdown(markdown)
            )

        except Exception as e:
            return VisionParseResult(
                page_num=page_num,
                markdown=original_text,
                quality_score=0.5,
                table_structures=[],
                error=str(e)
            )

    def _strip_thinking_tags(self, text: str) -> str:
        text = re.sub(r'<think>[\s\S]*?</think>', '', text)
        text = re.sub(r'<think>[\s\S]*?</think>', '', text)
        text = re.sub(r'```think[\s\S]*?```', '', text)
        return text.strip()

    def _extract_tables_from_markdown(self, markdown: str) -> List[List[List[str]]]:
        tables = []
        table_pattern = r'\|(.+)\|\n\|[-:\s|]+\|\n((?:\|.+\|\n)+)'
        matches = re.findall(table_pattern, markdown)
        for header, rows in matches:
            header_cells = [c.strip() for c in header.split('|') if c.strip()]
            table = [header_cells]
            for row in rows.strip().split('\n'):
                if row.strip():
                    cells = [c.strip() for c in row.split('|') if c.strip()]
                    if cells:
                        table.append(cells)
            if len(table) > 1:
                tables.append(table)
        return tables


def parse_with_vision_fallback(pdf_path: str, text_result: str, page_num: int = 1, garbage_threshold: float = 0.10) -> str:
    checker = VisionGateKeeper()
    if checker.needs_vision_parsing(text_result, 0):
        parser = VisionDocumentParser()
        result = parser.correct_page(pdf_path, page_num, text_result)
        if result.error is None and result.markdown:
            return result.markdown
    return text_result


def fix_garbled_words(pdf_path: str, garbled_text: str, page_num: int = 1, context: str = "") -> str:
    parser = VisionDocumentParser()
    result = parser.correct_page(pdf_path, page_num, garbled_text, context)
    return result.markdown if result.markdown else garbled_text