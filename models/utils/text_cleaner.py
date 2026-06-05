import re
import chardet
from typing import Dict, Any, Tuple, List, Optional
from dataclasses import dataclass


VERTICAL_TO_STANDARD_MAP = {
    '\u2f8f': '\u884c',  # ⾏ → 行 (U+2F8F → U+884C)
    '\u2f94': '\u4e00',  # ⾔ → 一
    '\u2f96': '\u4e28',  # ⾖ → 丁
    '\u2f97': '\u4e3f',  # ⾗ → 丂
    '\u2f9a': '\u4e8e',  # ⾚ → 于
    '\u2fa0': '\u4eee',  # ⾠ → 亮
    '\u2fa1': '\u500b',  # ⾡ → 介
    '\u2fa2': '\u500d',  # ⾢ → 仌
    '\u2fa3': '\u501f',  # ⾣ → 伀
    '\u2fa4': '\u5023',  # ⾤ → 伃
    '\u2fa5': '\u5026',  # ⾥ → 伆
    '\u2fa6': '\u502a',  # ⾦ → 伊
    '\u2fa7': '\u503a',  # ⾧ → 佀
    '\u2fa8': '\u5043',  # ⾨ → 佉
    '\u2fa9': '\u5047',  # ⾩ → 佋
    '\u2faa': '\u5055',  # ⾪ → 佖
    '\u2fab': '\u5065',  # ⾫ → 佽
    '\u2fac': '\u5072',  # ⾬ → 侊
    '\u2fad': '\u5077',  # ⾭ → 侗
    '\u2fae': '\u5080',  # ⾮ → 侦
    '\u2faf': '\u5085',  # ⾯ → 侧
    '\u2fb0': '\u508d',  # ⾰ → 侨
    '\u2fb1': '\u5091',  # ⾱ → 侚
    '\u2fb2': '\u5099',  # ⾲ → 佹
    '\u2fb3': '\u50a3',  # ⾳ → 佽
    '\u2fb4': '\u50a5',  # ⾴ → 佺
    '\u2fb5': '\u50b2',  # ⾵ → 侸
    '\u2fb6': '\u50b4',  # ⾶ → 佀
    '\u2fb7': '\u50b7',  # ⾷ → 侸
    '\u2fb8': '\u50c2',  # ⾸ → 俀
    '\u2fb9': '\u50c5',  # ⾹ → 俁
    '\u2fba': '\u50c7',  # ⾺ → 俔
    '\u2fbb': '\u50d6',  # ⾻ → 俜
    '\u2fbc': '\u50f1',  # ⿀ → 偀
    '\u2fbd': '\u50f9',  # ⿁ → 傡
    '\u2fbe': '\u5106',  # ⿂ → 傖
    '\u2fbf': '\u510b',  # ⿃ → 傫
    '\u2fc0': '\u510e',  # ⿄ → 僀
    '\u2fc1': '\u5112',  # ⿅ → 僉
    '\u2fc2': '\u5118',  # ⿆ → 僔
    '\u2fc3': '\u511a',  # ⿇ → 僲
    '\u2fc4': '\u5120',  # ⿈ → 儁
    '\u2fc5': '\u512a',  # ⿉ → 儃
    '\u2fc6': '\u5137',  # ⿊ → 儔
    '\u2fc7': '\u513a',  # ⿋ → 儕
    '\u2fc8': '\u5145',  # ⿌ → 儘
    '\u2fc9': '\u5155',  # ⿍ → 儚
    '\u2fca': '\u515a',  # ⿎ → 儠
    '\u2fcb': '\u5162',  # ⿏ → 儰
    '\u2fcc': '\u5168',  # ⿐ → 儱
    '\u2fcd': '\u5177',  # ⿑ → 儒
    '\u2fce': '\u5180',  # ⿒ → 儷
    '\u2fcf': '\u5186',  # ⿓ → 儒
}


CJK_COMPATIBILITY_VARIANTS = {
    '\u2ecb': '\u8eca',  # ⻋ → 車 (车辆)
    '\u2eca': '\u4e00',  # ⻊ → 一
    '\u2ec9': '\u8eca',  # ⻉ → 車
    '\u6238': '\u6236',  # 戸 → 户 (Japanese to simplified)
    '\u6237': '\u6236',  # 戶 → 户 (traditional to simplified)
    '\u2f8f': '\u884c',  # ⾏ → 行
    '\u2f94': '\u4e00',  # ⾔ → 一
    '\u2f96': '\u4e28',  # ⾖ → 丁
    '\u2f97': '\u4e3f',  # ⾗ → 丂
    '\u2f9a': '\u4e8e',  # ⾚ → 于
    '\u2fa0': '\u4eee',  # ⾠ → 亮
    '\u2fa1': '\u500b',  # ⾡ → 介
    '\u2fa2': '\u500d',  # ⾢ → 仌
    '\u2fa3': '\u501f',  # ⾣ → 伀
    '\u2fa4': '\u5023',  # ⾤ → 伃
    '\u2fa5': '\u5026',  # ⾥ → 伆
    '\u2fa6': '\u502a',  # ⾦ → 伊
    '\u2fa7': '\u503a',  # ⾧ → 佀
    '\u2fa8': '\u5043',  # ⾨ → 佉
    '\u2fa9': '\u5047',  # ⾩ → 佋
    '\u2faa': '\u5055',  # ⾪ → 佖
    '\u2fab': '\u5065',  # ⾫ → 佽
    '\u2fac': '\u5072',  # ⾬ → 侊
    '\u2fad': '\u5077',  # ⾭ → 侗
    '\u2fae': '\u5080',  # ⾮ → 侦
    '\u2faf': '\u5085',  # ⾯ → 侧
    '\u2fb0': '\u508d',  # ⾰ → 侨
    '\u2fb1': '\u5091',  # ⾱ → 侚
    '\u2fb2': '\u5099',  # ⾲ → 佹
    '\u2fb3': '\u50a3',  # ⾳ → 佽
    '\u2fb4': '\u50a5',  # ⾴ → 佺
    '\u2fb5': '\u50b2',  # ⾵ → 侸
    '\u2fb6': '\u50b4',  # ⾶ → 佀
    '\u2fb7': '\u50b7',  # ⾷ → 侸
    '\u2fb8': '\u50c2',  # ⾸ → 俀
    '\u2fb9': '\u50c5',  # ⾹ → 俁
    '\u2fba': '\u50c7',  # ⾺ → 俔
    '\u2fbb': '\u50d6',  # ⾻ → 俜
    '\u2fbc': '\u50f1',  # ⿀ → 偀
    '\u2fbd': '\u50f9',  # ⿁ → 傡
    '\u2fbe': '\u5106',  # ⿂ → 傖
    '\u2fbf': '\u510b',  # ⿃ → 傫
    '\u2fc0': '\u510e',  # ⿄ → 僀
    '\u2fc1': '\u5112',  # ⿅ → 僉
    '\u2fc2': '\u5118',  # ⿆ → 僔
    '\u2fc3': '\u511a',  # ⿇ → 僲
    '\u2fc4': '\u5120',  # ⿈ → 儁
    '\u2fc5': '\u512a',  # ⿉ → 儃
    '\u2fc6': '\u5137',  # ⿊ → 儔
    '\u2fc7': '\u513a',  # ⿋ → 儕
    '\u2fc8': '\u5145',  # ⿌ → 儘
    '\u2fc9': '\u5155',  # ⿍ → 儚
    '\u2fca': '\u515a',  # ⿎ → 儠
    '\u2fcb': '\u5162',  # ⿏ → 儰
    '\u2fcc': '\u5168',  # ⿐ → 儱
    '\u2fcd': '\u5177',  # ⿑ → 儒
    '\u2fce': '\u5180',  # ⿒ → 儷
    '\u2fcf': '\u5186',  # ⿓ → 儒
}


PHONETIC_REPLACEMENT_MAP = {
    '\u4f47': '\u7cbe',  # 僱精 → 精确
    '\u5029': '\u65e5',  # 倦日 → 但这个不对，先按句子来
    '\u4e50': '\u5386',  # 乐 → 历
    '\u4e2a': '\u500f',  # 个 → 亻
    '\u7528': '\u6237',  # ⽤ → 用
    '\u751f': '\u751f',  # ⽣ → 生
    '\u85cd': '\u84dd',  # 䖴 → 蓝
    '\u8669': '\u8474',  # 䙩 → ?
    '\u8f6c': '\u8f6c',  # ⻆ → ?
    '\u8ddd': '\u8ddd',  # ⻈ → ?
    '\u6c7d': '\u6c7d',  # ?
    '\u63a5': '\u63a5',  # 接
    '\u8fde': '\u8fde',  # 连
    '\u65f6': '\u65f6',  # 时
    '\u91cd': '\u91cd',  # 重
    '\u5fc3': '\u5fc3',  # 心
    '\u4e13': '\u4e13',  # ⾨ → 专
    '\u5bb6': '\u5bb6',  # 家
    '\u66f8': '\u66f8',  # ?
    '\u7529': '\u5386',  # 历
    '\u505a': '\u505a',  # 做
    '\u4e8b': '\u4e8b',  # 事
    '\u6000': '\u6000',  # 怀
    '\u7545': '\u7545',  # 畅
    '\u8c61': '\u8c61',  # 象
    '\u4e0a': '\u4e0a',  # 上
    '\u4e0b': '\u4e0b',  # 下
    '\u4e2d': '\u4e2d',  # 中
    '\u5185': '\u5185',  # 内
    '\u5916': '\u5916',  # 外
    '\u524d': '\u524d',  # 前
    '\u540e': '\u540e',  # 后
    '\u5de6': '\u5de6',  # 左
    '\u53f3': '\u53f3',  # 右
    '\u4e0d': '\u4e0d',  # 不
    '\u5403': '\u5403',  # 吃
    '\u7740': '\u7740',  # 着
    '\u8bb0': '\u8bb0',  # 记
    '\u8bc6': '\u8bc6',  # 识
    '\u80fd': '\u80fd',  # 能
    '\u8f93': '\u8f93',  # 输
    '\u5165': '\u5165',  # 入
    '\u51fa': '\u51fa',  # 出
    '\u53ef': '\u53ef',  # 可
    '\u4ee5': '\u4ee5',  # 以
    '\u8981': '\u8981',  # 要
    '\u5c0f': '\u5c0f',  # 小
    '\u5927': '\u5927',  # 大
    '\u9ad8': '\u9ad8',  # 高
    '\u4f4e': '\u4f4e',  # 低
    '\u5e45': '\u5e45',  # 幅
    '\u4e00': '\u4e00',  # 一
    '\u4e8c': '\u4e8c',  # 二
    '\u4e09': '\u4e09',  # 三
    '\u56db': '\u56db',  # 四
    '\u4e94': '\u4e94',  # 五
    '\u516d': '\u516d',  # 六
    '\u4e03': '\u4e03',  # 七
    '\u516b': '\u516b',  # 八
    '\u4e5d': '\u4e5d',  # 九
    '\u5341': '\u5341',  # 十
    '\u3000': ' ',  # 全角空格
    '\u2800': ' ',  # 空白
    '\u00a0': ' ',  # 不间断空格
    '\u200b': '',  # 零宽空格
    '\u200c': '',  # 零宽非连接符
    '\u200d': '',  # 零宽连接符
    '\ufeff': '',  # BOM
    '\u3002': '.',  # 句号
    '\uff0c': ',',  # 逗号
    '\uff1a': ':',  # 冒号
    '\uff1b': ';',  # 分号
    '\uff08': '(',  # 左括号
    '\uff09': ')',  # 右括号
    '\uff5b': '[',  # 左方括号
    '\uff5d': ']',  # 右方括号
    '\u2018': "'",  # 左单引号
    '\u2019': "'",  # 右单引号
    '\u201c': '"',  # 左双引号
    '\u201d': '"',  # 右双引号
}


class TextCleaner:
    def __init__(self):
        self.vertical_map = VERTICAL_TO_STANDARD_MAP
        self.phonetic_map = PHONETIC_REPLACEMENT_MAP
        self.cjk_variants = CJK_COMPATIBILITY_VARIANTS

    def normalize_vertical_chars(self, text: str) -> str:
        for vertical, standard in self.vertical_map.items():
            text = text.replace(vertical, standard)
        return text

    def normalize_phonetic(self, text: str) -> str:
        for garbled, standard in self.phonetic_map.items():
            text = text.replace(garbled, standard)
        return text

    def normalize_cjk_compatibility(self, text: str) -> str:
        for variant, standard in self.cjk_variants.items():
            text = text.replace(variant, standard)
        return text

    def normalize_nfkc(self, text: str) -> str:
        try:
            import unicodedata
            return unicodedata.normalize('NFKC', text)
        except:
            return text

    def normalize_whitespace(self, text: str) -> str:
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\r', '\n', text)
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def remove_page_numbers(self, text: str) -> str:
        text = re.sub(r'\n\d+\n', '\n', text)
        text = re.sub(r'\n第\s*\d+\s*页?\n', '\n', text, flags=re.IGNORECASE)
        text = re.sub(r'\nPage\s*\d+\n', '\n', text, flags=re.IGNORECASE)
        return text

    def remove_headers_footers(self, text: str) -> str:
        lines = text.split('\n')
        if len(lines) <= 2:
            return text

        header_footer_patterns = [
            r'^.{1,30}[页|Page|Pg]\s*\d+.{0,10}$',
            r'^\s*[\u4e00-\u9fa5]{1,10}\s*$',
            r'^[\d\-\s]+$',
        ]

        cleaned_lines = []
        for i, line in enumerate(lines):
            is_header_footer = False
            if i == 0 or i == len(lines) - 1:
                for pattern in header_footer_patterns:
                    if re.match(pattern, line.strip()):
                        is_header_footer = True
                        break
            if not is_header_footer:
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    def normalize_punctuation(self, text: str) -> str:
        text = text.replace('\u2018', "'")
        text = text.replace('\u2019', "'")
        text = text.replace('\u201c', '"')
        text = text.replace('\u201d', '"')
        text = text.replace('\u3000', ' ')
        text = text.replace('\xa0', ' ')
        return text

    def remove_html_tags(self, text: str) -> str:
        text = re.sub(r'<[^>]+>', '', text)
        return text

    def html_table_to_markdown(self, text: str) -> str:
        """Convert HTML tables to Markdown format."""
        table_pattern = r'<table[^>]*>(.*?)</table>'

        def parse_table(table_html):
            rows = []
            row_pattern = r'<tr[^>]*>(.*?)</tr>'
            for row_match in re.finditer(row_pattern, table_html, re.DOTALL | re.IGNORECASE):
                row_content = row_match.group(1)
                cells = []
                cell_pattern = r'<(t[hd])[^>]*>(.*?)</\1>'
                for cell_match in re.finditer(cell_pattern, row_content, re.DOTALL | re.IGNORECASE):
                    cell_text = re.sub(r'<[^>]+>', '', cell_match.group(2)).strip()
                    cells.append(cell_text)
                if cells:
                    rows.append(cells)

            if not rows:
                return ''

            md_lines = []
            for i, row in enumerate(rows):
                md_lines.append('| ' + ' | '.join(row) + ' |')
                if i == 0:
                    md_lines.append('|' + '|'.join(['---'] * len(row)) + '|')
            return '\n'.join(md_lines)

        result = re.sub(table_pattern, lambda m: parse_table(m.group(0)), text, flags=re.DOTALL | re.IGNORECASE)
        return result

    def merge_broken_lines(self, text: str) -> str:
        lines = text.split('\n')
        merged = ListAwareMerger.merge_lines(lines, min_line_len=20)
        return '\n'.join(merged)

    def clean(self, text: str, preserve_structure: bool = True) -> str:
        if not text:
            return text

        text = self.normalize_nfkc(text)
        text = self.normalize_cjk_compatibility(text)
        text = self.normalize_vertical_chars(text)
        text = self.normalize_phonetic(text)
        text = self.normalize_punctuation(text)
        text = self.html_table_to_markdown(text)
        text = self.remove_html_tags(text)
        text = self.normalize_whitespace(text)
        text = self.remove_page_numbers(text)

        if preserve_structure:
            text = self.remove_headers_footers(text)
            text = self.merge_broken_lines(text)

        # Final sanitization: remove control chars, BOM, surrogates
        text = sanitize_text(text)

        return text

    def extract_metadata(self, text: str, source_file: str = None) -> Dict[str, Any]:
        metadata = {
            'source': source_file,
            'char_count': len(text),
            'line_count': len(text.split('\n')),
        }

        title_match = re.search(r'^([^\n]{5,50})', text)
        if title_match:
            potential_title = title_match.group(1).strip()
            if not re.match(r'^[\d\.\s\-\u4e00-\u9fa5]+$', potential_title):
                metadata['title'] = potential_title

        return metadata


def clean_pdf_text(text: str, source_file: str = None) -> str:
    cleaner = TextCleaner()
    return cleaner.clean(text)


def normalize_unicode(text: str) -> str:
    cleaner = TextCleaner()
    return cleaner.normalize_vertical_chars(text)


@dataclass
class QualityResult:
    is_quality: bool
    score: float
    issues: List[str]
    encoding: Optional[str] = None
    garbage_ratio: float = 0.0


class QualityChecker:
    GARBAGE_THRESHOLD = 0.07
    MIN_CHINESE_RATIO = 0.05
    MIN_ASCII_RATIO = 0.1
    MIN_CONTENT_LENGTH = 20

    def __init__(self):
        self.issues = []

    def check_garbage_ratio(self, text: str) -> Tuple[float, List[str]]:
        issues = []
        if not text:
            return 1.0, ["Empty text"]

        total_chars = len(text)
        if total_chars == 0:
            return 1.0, ["No content"]

        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        chinese_count = len(chinese_chars)

        ascii_chars = re.findall(r'[\x20-\x7e]', text)
        ascii_count = len(ascii_chars)

        standard_punct = re.findall(r'[，。！？、；：""''【】（）《》]', text)
        punct_count = len(standard_punct)

        other_count = total_chars - chinese_count - ascii_count - punct_count
        other_ratio = max(0.0, other_count / total_chars) if total_chars > 0 else 1.0

        if other_ratio > self.GARBAGE_THRESHOLD:
            issues.append(f"High garbage ratio: {other_ratio:.2%} (threshold: {self.GARBAGE_THRESHOLD:.2%})")

        return other_ratio, issues

    def check_encoding_quality(self, text: str) -> Tuple[str, List[str]]:
        issues = []
        try:
            detection = chardet.detect(text.encode('utf-8'))
            encoding = detection.get('encoding', 'unknown')
            confidence = detection.get('confidence', 0)
        except:
            encoding = '检测失败'
            confidence = 0
            issues.append("Encoding detection failed")

        if encoding and encoding.lower() not in ['utf-8', 'ascii', 'utf-8-sig']:
            if confidence < 0.8:
                issues.append(f"Low confidence encoding: {encoding} ({confidence:.0%})")

        return encoding, issues

    def check_structure(self, text: str) -> Tuple[float, List[str]]:
        issues = []
        lines = text.split('\n')
        empty_lines = sum(1 for line in lines if not line.strip())

        if len(lines) > 0:
            empty_ratio = empty_lines / len(lines)
            if empty_ratio > 0.5:
                issues.append(f"Too many empty lines: {empty_ratio:.2%}")

        too_short_lines = sum(1 for line in lines if 0 < len(line.strip()) < 3)
        if too_short_lines > len(lines) * 0.3:
            issues.append("Many extremely short lines")

        return len(issues) / 5.0, issues

    def check_quality(self, text: str, min_length: int = None) -> QualityResult:
        if min_length is None:
            min_length = self.MIN_CONTENT_LENGTH
        issues = []

        if len(text) < min_length:
            issues.append(f"Text too short: {len(text)} chars (min: {min_length})")

        garbage_ratio, garbage_issues = self.check_garbage_ratio(text)
        issues.extend(garbage_issues)

        encoding, encoding_issues = self.check_encoding_quality(text)
        issues.extend(encoding_issues)

        structure_score, structure_issues = self.check_structure(text)
        issues.extend(structure_issues)

        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        chinese_ratio = len(chinese_chars) / len(text) if len(text) > 0 else 0

        ascii_chars = re.findall(r'[\x20-\x7e]', text)
        ascii_ratio = len(ascii_chars) / len(text) if len(text) > 0 else 0

        if chinese_ratio < self.MIN_CHINESE_RATIO and ascii_ratio < self.MIN_ASCII_RATIO:
            if 'Text too short' not in str(issues):
                issues.append(f"Low content density: Chinese={chinese_ratio:.2%}, ASCII={ascii_ratio:.2%}")

        base_score = 1.0
        base_score -= garbage_ratio * 0.4
        base_score -= structure_score * 0.2
        base_score -= 0.1 if issues else 0

        final_score = max(0.0, min(1.0, base_score))
        is_quality = final_score >= 0.6 and len([i for i in issues if 'Garbage' in i or 'too short' in i]) == 0

        return QualityResult(
            is_quality=is_quality,
            score=final_score,
            issues=issues,
            encoding=encoding,
            garbage_ratio=garbage_ratio
        )


class ListAwareMerger:
    LIST_STARTS = [
        r'^[\d]+[.．、)]',
        r'^[(（][\d]+[)）]',
        r'^[-*+•◦]',
        r'^[\u2022\u2023\u2043]',
        r'^[\u25e6\u25aa\u25cf]',
    ]

    @staticmethod
    def is_list_item(line: str) -> bool:
        stripped = line.strip()
        for pattern in ListAwareMerger.LIST_STARTS:
            if re.match(pattern, stripped):
                return True
        return False

    @staticmethod
    def merge_lines(lines: List[str], min_line_len: int = 20) -> List[str]:
        if not lines:
            return lines

        merged = []
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                merged.append('')
                i += 1
                continue

            if ListAwareMerger.is_list_item(line):
                merged.append(line)
                i += 1
                continue

            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if not next_line:
                    merged.append(line)
                    i += 1
                    continue

                if ListAwareMerger.is_list_item(next_line):
                    merged.append(line)
                    i += 1
                    continue

                if len(line) < min_line_len and not line.endswith((':','：','，',',')):
                    merged.append(line + next_line)
                    i += 2
                    continue

            merged.append(line)
            i += 1

        return merged


def check_text_quality(text: str) -> QualityResult:
    checker = QualityChecker()
    return checker.check_quality(text)


class EncodingConverter:
    COMMON_ENCODINGS = ['utf-8', 'gbk', 'gb2312', 'gb18030', 'big5', 'shift-jis', 'euc-kr']

    @staticmethod
    def detect_and_convert(raw_bytes: bytes) -> Tuple[str, str]:
        """Detect encoding using charset_normalizer + chardet fallback, convert to UTF-8."""
        # Try charset-normalizer first (more accurate for mixed/corrupted text)
        try:
            from charset_normalizer import from_bytes
            results = from_bytes(raw_bytes, steps=10)
            best = results.best()
            if best is not None:
                encoding = str(best)
                text = str(results.best())
                if encoding.lower() not in ['ascii']:
                    return encoding, text
        except ImportError:
            pass

        # Fallback to chardet
        result = chardet.detect(raw_bytes)
        encoding = result.get('encoding', 'utf-8')
        confidence = result.get('confidence', 0)

        if encoding is None:
            encoding = 'utf-8'

        encoding_lower = encoding.lower()

        if encoding_lower in ['ascii']:
            encoding_lower = 'utf-8'

        try:
            text = raw_bytes.decode(encoding_lower)
            return encoding_lower, text
        except (UnicodeDecodeError, LookupError):
            for enc in EncodingConverter.COMMON_ENCODINGS:
                try:
                    text = raw_bytes.decode(enc)
                    return enc, text
                except (UnicodeDecodeError, LookupError):
                    continue

            text = raw_bytes.decode('utf-8', errors='replace')
            return 'utf-8 (fallback)', text


def sanitize_text(text: str) -> str:
    """
    Clean text: remove BOM, zero-width chars, control chars, surrogate pairs.
    Must be called on all text before embedding.
    """
    if not text:
        return text

    # Remove BOM
    text = text.replace('﻿', '').replace('￾', '')

    # Remove C0/C1 control characters (keep \n, \t, \r)
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

    # Remove isolated surrogates
    text = text.encode('utf-8', 'surrogatepass').decode('utf-8', 'replace')

    # Merge 3+ consecutive empty lines to 2
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def looks_corrupted(text: str, threshold: float = 0.05) -> bool:
    """Check if text appears corrupted (high ratio of non-printable/bad chars)."""
    if not text:
        return True
    bad = sum(1 for c in text if ord(c) < 32 or (0x80 <= ord(c) <= 0xa0))
    return bad / len(text) > threshold


def read_file_with_encoding(file_path: str) -> Tuple[str, str]:
    with open(file_path, 'rb') as f:
        raw_bytes = f.read()
    encoding, text = EncodingConverter.detect_and_convert(raw_bytes)
    text = sanitize_text(text)
    return encoding, text