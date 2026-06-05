import json
import os
import time
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
import requests
import sys

sys.path.insert(0, r'D:\workspace\Agent')
from config import MINIMAX_API_KEY, MINIMAX_BASE_URL, PROXIES, PADDLEOCR_TOKEN, PADDLEOCR_API_URL, PADDLEOCR_MODEL


@dataclass
class PaddleOCRResult:
    page_num: int
    markdown_text: str
    images: Dict[str, str]
    output_images: Dict[str, str]
    raw_result: Dict[str, Any]


@dataclass
class MetadataTag:
    department: Optional[str] = None
    doc_type: Optional[str] = None
    confidentiality: Optional[str] = None
    time_period: Optional[str] = None
    source_file: Optional[str] = None
    page_num: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in {
            'department': self.department,
            'doc_type': self.doc_type,
            'confidentiality': self.confidentiality,
            'time_period': self.time_period,
            'source_file': self.source_file,
            'page_num': self.page_num
        }.items() if v is not None}


class PaddleOCRParser:
    def __init__(self, output_dir: str = "knowledge_base/raw/paddleocr_output"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.session = requests.Session()
        if PROXIES:
            self.session.proxies = PROXIES
        else:
            self.session.trust_env = False

    def parse_pdf(self, file_path: str, use_chart_recognition: bool = False) -> List[PaddleOCRResult]:
        headers = {
            "Authorization": f"bearer {PADDLEOCR_TOKEN}",
        }

        optional_payload = {
            "useDocOrientationClassify": False,
            "useDocUnwarping": False,
            "useChartRecognition": use_chart_recognition,
        }

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        data = {
            "model": PADDLEOCR_MODEL,
            "optionalPayload": json.dumps(optional_payload)
        }

        with open(file_path, "rb") as f:
            files = {"file": f}
            job_response = self.session.post(PADDLEOCR_API_URL, headers=headers, data=data, files=files)

        if job_response.status_code != 200:
            raise Exception(f"PaddleOCR API error: {job_response.status_code} - {job_response.text}")

        job_id = job_response.json()["data"]["jobId"]
        print(f"[PaddleOCR] Job submitted: {job_id}")

        jsonl_url = self._poll_job_status(job_id, headers)
        if not jsonl_url:
            return []

        return self._download_results(jsonl_url)

    def _poll_job_status(self, job_id: str, headers: Dict) -> Optional[str]:
        while True:
            job_result = self.session.get(f"{PADDLEOCR_API_URL}/{job_id}", headers=headers)
            if job_result.status_code != 200:
                print(f"[PaddleOCR] Polling error: {job_result.status_code}")
                break

            result_json = job_result.json()
            state = result_json["data"]["state"]

            if state == 'pending':
                print("[PaddleOCR] Job pending...")
            elif state == 'running':
                try:
                    progress = result_json['data'].get('extractProgress', {})
                    total = progress.get('totalPages', 0)
                    extracted = progress.get('extractedPages', 0)
                    print(f"[PaddleOCR] Running... pages: {extracted}/{total}")
                except (KeyError, TypeError):
                    print("[PaddleOCR] Running...")
            elif state == 'done':
                try:
                    progress = result_json['data'].get('extractProgress', {})
                    extracted = progress.get('extractedPages', 0)
                    start_time = progress.get('startTime', 'N/A')
                    end_time = progress.get('endTime', 'N/A')
                    print(f"[PaddleOCR] Done! Extracted {extracted} pages, start: {start_time}, end: {end_time}")
                except (KeyError, TypeError):
                    print(f"[PaddleOCR] Done! pages: {extracted if 'extracted' in dir() else 'N/A'}")
                return result_json['data']['resultUrl']['jsonUrl']
            elif state == "failed":
                error = result_json['data'].get('errorMsg', 'Unknown error')
                print(f"[PaddleOCR] Failed: {error}")
                return None

            time.sleep(5)

    def _download_results(self, jsonl_url: str) -> List[PaddleOCRResult]:
        response = self.session.get(jsonl_url)
        response.raise_for_status()
        response.encoding = 'utf-8'
        lines = response.text.strip().split('\n')

        results = []
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            result_data = json.loads(line)["result"]
            for i, res in enumerate(result_data["layoutParsingResults"]):
                markdown_text = res["markdown"]["text"]

                filtered_images = {}
                for img_path, img_url in res["markdown"].get("images", {}).items():
                    if 'layout_det_res' not in img_path.lower():
                        filtered_images[img_path] = img_url

                page_result = PaddleOCRResult(
                    page_num=line_num * 100 + i,
                    markdown_text=markdown_text,
                    images=filtered_images,
                    output_images=res.get("outputImages", {}),
                    raw_result=res
                )
                results.append(page_result)

        return results

    def _save_image(self, url: str, filename: str) -> Optional[str]:
        try:
            response = self.session.get(url)
            if response.status_code == 200:
                full_path = os.path.join(self.output_dir, filename)
                os.makedirs(os.path.dirname(full_path), exist_ok=True)
                with open(full_path, "wb") as f:
                    f.write(response.content)
                print(f"[PaddleOCR] Image saved: {full_path}")
                return full_path
        except Exception as e:
            print(f"[PaddleOCR] Image save error: {e}")
        return None


class LLMMetadataTagger:
    def __init__(self, api_key: str = None, base_url: str = None):
        self.api_key = api_key or MINIMAX_API_KEY
        self.base_url = base_url or MINIMAX_BASE_URL

    def extract_metadata(self, text: str, source_file: str = "") -> MetadataTag:
        system_prompt = """你是一个元数据提取助手。你的输出**必须**是有效的JSON格式，不要包含任何其他文字。
输出格式（必须是这个JSON，不能有其他内容）：
{"department": "...", "doc_type": "...", "confidentiality": "...", "time_period": "..."}"""

        user_prompt = f"""分析以下文档内容，提取元数据标签。

文档来源: {source_file}
文档内容预览:
{text[:2000]}

请提取以下元数据（如果无法确定，标记为null）：
- department: 部门名称，如"财务部"、"技术部"、"管理部"等
- doc_type: 文档类型，如"周报"、"月报"、"协议"、"规范"、"手册"等
- confidentiality: 密级，如"公开"、"内部"、"机密"等
- time_period: 时间期间，如"2024-Q3"、"2024年"等，使用标准格式

输出格式（必须是JSON，不能有其他内容）：
{{"department": "...", "doc_type": "...", "confidentiality": "...", "time_period": "..."}}"""

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "MiniMax-M2.7",
                "max_tokens": 200,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }

            session = requests.Session()
            if PROXIES:
                session.proxies = PROXIES
            else:
                session.trust_env = False

            response = session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=(10, 30)
            )

            if response.status_code == 200:
                try:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[LLMMetadataTagger] JSON parse error: {e}, response text: {response.text[:200]}")
                    return MetadataTag(source_file=source_file)
                return self._parse_metadata_tag(content, source_file)
        except Exception as e:
            print(f"[LLMMetadataTagger] Error: {e}")

        return MetadataTag(source_file=source_file)

    def _clean_thinking_tags(self, content: str) -> str:
        """Remove <think>...</think> thinking tags from content"""
        import re
        # Use simpler pattern that works with Chinese characters
        pattern = r'<think>[^"]*?(?:<[^"]*?>)*[^"]*?</think>'
        cleaned = re.sub(pattern, '', content, flags=re.IGNORECASE)
        # Also remove any remaining <think> and ]]> tags
        cleaned = cleaned.replace('<think>', '').replace('</think>', '')
        return cleaned.strip()

    def _extract_json_from_text(self, content: str) -> Optional[Dict]:
        """从混杂文本中提取JSON，适配不遵循纯JSON约束的模型"""
        import re

        # 方法1：查找代码块内的JSON
        json_block_pattern = r'```(?:json)?\s*\n?([^{}]*\{[^{}]*\}[^{}]*)\n?```'
        for match in re.finditer(json_block_pattern, content, re.DOTALL):
            try:
                return json.loads(match.group(1))
            except (json.JSONDecodeError, KeyError):
                pass

        # 方法2：查找所有 {...} 模式的JSON对象
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        for match in re.finditer(json_pattern, content):
            json_str = match.group()
            try:
                result = json.loads(json_str)
                # 验证是否包含预期的键
                if any(key in result for key in ['department', 'headings', 'summary', 'key_terms']):
                    return result
            except json.JSONDecodeError:
                pass

        # 方法3：如果文本中有明确标记的JSON区域（包含 "{" 的区域）
        json_start = content.find('{"')
        if json_start >= 0:
            # 尝试找到完整的JSON（带括号匹配）
            depth = 0
            for i, c in enumerate(content[json_start:], json_start):
                if c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(content[json_start:i+1])
                        except json.JSONDecodeError:
                            break

        return None

    def _parse_metadata_tag(self, content: str, source_file: str) -> MetadataTag:
        content = self._clean_thinking_tags(content).strip()

        # 先尝试提取JSON
        extracted = self._extract_json_from_text(content)
        if extracted and isinstance(extracted, dict):
            return MetadataTag(
                department=extracted.get("department"),
                doc_type=extracted.get("doc_type"),
                confidentiality=extracted.get("confidentiality"),
                time_period=extracted.get("time_period"),
                source_file=source_file
            )

        # JSON提取失败，从文本中提取关键信息作为fallback
        return self._parse_metadata_from_text(content, source_file)

    def _parse_metadata_from_text(self, content: str, source_file: str) -> MetadataTag:
        """从非结构化文本中提取元数据的fallback方法"""
        import re

        metadata = {}

        # 尝试提取 department
        dept_patterns = [
            r'部门[：:]\s*"?([^",\n]+)"?',
            r'department[：:]\s*"?([^",\n]+)"?',
            r'技术[部]*(研发|测试|产品)?部',
        ]
        for pattern in dept_patterns:
            match = re.search(pattern, content)
            if match:
                metadata['department'] = match.group(1).strip()
                break

        # 尝试提取 doc_type
        doc_patterns = [
            r'文档类型[：:]\s*"?([^",\n]+)"?',
            r'doc_type[：:]\s*"?([^",\n]+)"?',
            r'(技术文档|协议文档|规范|手册|说明书|报告|周报|月报)',
        ]
        for pattern in doc_patterns:
            match = re.search(pattern, content)
            if match:
                metadata['doc_type'] = match.group(1).strip()
                break

        # 尝试提取 confidentiality
        conf_patterns = [
            r'保密级别[：:]\s*"?([^",\n]+)"?',
            r'(公开|内部|机密|秘密)',
        ]
        for pattern in conf_patterns:
            match = re.search(pattern, content)
            if match:
                metadata['confidentiality'] = match.group(1).strip()
                break

        return MetadataTag(
            department=metadata.get("department"),
            doc_type=metadata.get("doc_type"),
            confidentiality=metadata.get("confidentiality"),
            time_period=metadata.get("time_period"),
            source_file=source_file
        )

    def _parse_content_from_text(self, content: str) -> Dict[str, Any]:
        """从非结构化文本中提取内容的fallback方法"""
        import re

        result = {
            "headings": [],
            "tables": [],
            "code_blocks": [],
            "key_terms": [],
            "summary": ""
        }

        # 提取标题（以 # 开头的行，排除Page N格式）
        heading_pattern = r'^#+\s*(.+)$'
        page_pattern = r'^Page\s*\d+$'
        for line in content.split('\n'):
            match = re.match(heading_pattern, line.strip())
            if match:
                heading_text = match.group(1).strip()
                # 过滤掉Page N和太长的标题
                if len(heading_text) < 50 and heading_text not in result["headings"]:
                    if not re.match(page_pattern, heading_text):
                        result["headings"].append(heading_text)

        # 提取关键术语（常见的BLE/物联网相关术语）
        term_patterns = [
            r'\b(BLE|Bluetooth|HID|RSSI|IOT|BLE|BTstack)\b',
            r'\b(OTA|DFU|升级|固件)\b',
            r'\b(CAN|UART|SPI|I2C|串口)\b',
            r'\b(蓝牙|WiFi|无线)\b',
            r'\b(控制器|MCU|BMS|电池)\b',
        ]
        found_terms = set()
        for pattern in term_patterns:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                term = match.group().strip()
                if term and len(term) > 2:
                    found_terms.add(term)
        result["key_terms"] = list(found_terms)[:10]

        # 提取摘要（第一段非HTML非标题的文字）
        paragraphs = content.split('\n\n')
        for para in paragraphs:
            para = para.strip()
            # 跳过HTML表格、太短的或标题
            if len(para) > 50 and not para.startswith('#') and not para.startswith('```') and not para.startswith('<table') and not '<td' in para:
                # 清理特殊字符
                summary = re.sub(r'[*#\[\]`]', '', para)
                result["summary"] = summary[:200]
                break

        return result

    def reorganize_content(self, markdown_text: str, page_num: int = 0) -> Dict[str, Any]:
        system_prompt = """你是一个结构化处理助手。你的输出**必须**是有效的JSON格式，不要包含任何其他文字。
输出格式（必须是这个JSON，不能有其他内容）：
{"headings": ["标题1", "标题2", ...], "tables": ["表格1的Markdown", "表格2的Markdown", ...], "code_blocks": ["代码块1", "代码块2", ...], "key_terms": ["术语1", "术语2", ...], "summary": "本页内容摘要"}"""

        user_prompt = f"""分析以下Markdown内容，进行结构化处理。

页码: {page_num}

内容:
{markdown_text}

任务:
1. 识别表格并转换为标准Markdown表格格式
2. 识别标题层级，构建目录结构
3. 识别关键术语并标注
4. 识别代码块并标注语言

输出格式（必须是JSON，不能有其他内容）：
{{"headings": ["标题1", "标题2", ...], "tables": ["表格1的Markdown", "表格2的Markdown", ...], "code_blocks": ["代码块1", "代码块2", ...], "key_terms": ["术语1", "术语2", ...], "summary": "本页内容摘要"}}"""

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "MiniMax-M2.7",
                "max_tokens": 800,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }

            session = requests.Session()
            if PROXIES:
                session.proxies = PROXIES
            else:
                session.trust_env = False

            response = session.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=(10, 60)
            )

            if response.status_code == 200:
                try:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                except (json.JSONDecodeError, KeyError) as e:
                    print(f"[LLMMetadataTagger] Reorganize JSON error: {e}, response: {response.text[:200]}")
                    return {"headings": [], "tables": [], "code_blocks": [], "key_terms": [], "summary": ""}
                content = self._clean_thinking_tags(content).strip()

                # 使用统一的JSON提取方法（适配不遵循纯JSON约束的模型）
                extracted = self._extract_json_from_text(content)
                if extracted and isinstance(extracted, dict) and 'summary' in extracted:
                    return {
                        "headings": extracted.get("headings", []),
                        "tables": extracted.get("tables", []),
                        "code_blocks": extracted.get("code_blocks", []),
                        "key_terms": extracted.get("key_terms", []),
                        "summary": extracted.get("summary", "")
                    }

                # Fallback: 使用原文分析提取标题和关键术语（而非LLM响应）
                return self._parse_content_from_text(markdown_text)
        except Exception as e:
            print(f"[LLMMetadataTagger] Reorganize error: {e}")

        return {"headings": [], "tables": [], "code_blocks": [], "key_terms": [], "summary": ""}


class EnhancedPDFParser:
    def __init__(self, output_dir: str = None):
        self.paddle_parser = PaddleOCRParser(output_dir)
        self.metadata_tagger = LLMMetadataTagger()
        self.output_dir = output_dir

    def parse_and_process(self, file_path: str, use_llm_reorganize: bool = True) -> List[Dict[str, Any]]:
        print(f"[EnhancedPDFParser] Parsing: {file_path}")
        ocr_results = self.paddle_parser.parse_pdf(file_path)

        all_content = []
        all_tables = []
        all_images = []
        first_title = "Untitled"

        for result in ocr_results:
            if not result.markdown_text.strip():
                continue

            page_title = self._extract_title(result.markdown_text)
            if first_title == "Untitled" and page_title != "Untitled":
                first_title = page_title

            all_content.append(f"\n\n## Page {result.page_num}\n\n{result.markdown_text}")

        full_content = "\n".join(all_content)

        metadata = self.metadata_tagger.extract_metadata(full_content, source_file=file_path)
        metadata.page_num = 0

        block = {
            'id': f"paddleocr_{hash(file_path)}",
            'type': 'protocol_doc',
            'title': first_title,
            'content': full_content,
            'source_file': file_path,
            'metadata': metadata.to_dict(),
            'page_num': 0,
            'images': all_images,
            'tables': all_tables,
        }

        if use_llm_reorganize and len(full_content) > 100:
            reorganized = self.metadata_tagger.reorganize_content(full_content, 0)
            block['reorganized'] = reorganized
            block['headings'] = reorganized.get('headings', [])
            block['key_terms'] = reorganized.get('key_terms', [])
            block['summary'] = reorganized.get('summary', '')

        return [block]

    def _extract_title(self, text: str) -> str:
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line.startswith('#'):
                return line.lstrip('#').strip()
            if line and len(line) < 100:
                return line
        return "Untitled"


def parse_with_paddleocr(file_path: str, output_dir: str = None) -> List[Dict[str, Any]]:
    if output_dir is None:
        pdf_name = os.path.splitext(os.path.basename(file_path))[0]
        output_dir = os.path.join(os.path.dirname(file_path), f"{pdf_name}_paddleocr")
    os.makedirs(output_dir, exist_ok=True)
    parser = EnhancedPDFParser(output_dir)
    blocks = parser.parse_and_process(file_path)

    if blocks:
        block = blocks[0]
        md_file = os.path.join(output_dir, 'content.md')
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(f'# {block["title"]}\n\n')
            f.write(f'**元数据**: {block["metadata"]}\n\n')
            if block.get('images'):
                f.write(f'**图片**: {block["images"]}\n\n')
            if block.get('summary'):
                f.write(f'**摘要**: {block["summary"]}\n\n')
            f.write('---\n\n')
            f.write(block['content'])
        print(f"[PaddleOCR] Content saved to: {md_file}")

    return blocks


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python paddleocr_parser.py <pdf_file>")
        print("Or import and use: parse_with_paddleocr(pdf_path)")
    else:
        pdf_path = sys.argv[1]
        blocks = parse_with_paddleocr(pdf_path)
        print(f"\nParsed {len(blocks)} blocks")
        for block in blocks[:3]:
            print(f"  - {block['title']} ({block['page_num']})")
            print(f"    Metadata: {block['metadata']}")
            print(f"    Tables: {len(block.get('tables', []))}")
            print(f"    Images: {len(block.get('images', []))}")