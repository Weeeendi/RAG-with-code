"""
PDF预检脚本：判断PDF是纯文本型还是复杂表格/图片型
用于决定使用pdfplumber还是PaddleOCR解析
"""
import os
import sys

def analyze_pdf_complexity(file_path: str) -> dict:
    """
    分析PDF复杂度
    返回: {
        'is_complex': bool,  # 是否复杂（大量表格/图片）
        'table_count': int,  # 表格数量估计
        'image_count': int, # 图片数量估计
        'text_ratio': float, # 文本占比
        'recommendation': str  # 'pdfplumber' or 'paddleocr'
    }
    """
    try:
        import pdfplumber
    except ImportError:
        return {
            'is_complex': False,
            'table_count': 0,
            'image_count': 0,
            'text_ratio': 1.0,
            'recommendation': 'paddleocr',  # 默认用OCR
            'error': 'pdfplumber not installed'
        }

    table_count = 0
    image_count = 0
    text_chars = 0
    total_elements = 0

    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:5]:  # 只检查前5页
                if page.tables:
                    table_count += len(page.tables)
                if page.images:
                    image_count += len(page.images)

                # 检查文本质量（乱码率）
                text = page.extract_text() or ""
                text_chars += len(text)

                # 检查是否包含常见乱码模式（表格图片的标志）
                if 'Bit7' in text or 'Bit6' in text or 'PGN' in text:
                    # 这些通常是表格内容
                    total_elements += 1

                if 'colspan' in text or 'rowspan' in text or '<td>' in text:
                    # HTML表格标签，说明是OCR输出
                    table_count += 1

                total_elements += 1
    except Exception as e:
        return {
            'is_complex': True,
            'table_count': 0,
            'image_count': 0,
            'text_ratio': 0.0,
            'recommendation': 'paddleocr',
            'error': str(e)
        }

    # 判断逻辑
    # 复杂: 表格多(>3) OR 图片多(>5) OR 文本少但有表格特征
    is_complex = table_count > 3 or image_count > 5

    # 如果文本极少但有表格特征，说明可能是图片表格
    if text_chars < 500 and table_count > 0:
        is_complex = True

    recommendation = 'paddleocr' if is_complex else 'pdfplumber'

    return {
        'is_complex': is_complex,
        'table_count': table_count,
        'image_count': image_count,
        'text_ratio': text_chars / max(total_elements * 100, 1),
        'recommendation': recommendation,
        'error': None
    }


def analyze_pdf_from_file_path(file_path: str) -> dict:
    """从文件路径分析PDF"""
    result = analyze_pdf_complexity(file_path)
    filename = os.path.basename(file_path)
    print(f"{filename}:")
    print(f"  - 表格数量: {result['table_count']}")
    print(f"  - 图片数量: {result['image_count']}")
    print(f"  - 文本字符: {result.get('text_chars', 'N/A')}")
    print(f"  - 推荐解析器: {result['recommendation']}")
    print(f"  - 复杂度: {'复杂' if result['is_complex'] else '简单'}")
    if result.get('error'):
        print(f"  - 错误: {result['error']}")
    print()
    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 分析protocol_docs目录下的所有PDF
        import glob
        pdf_dir = "knowledge_base/raw/protocol_docs"
        pdfs = glob.glob(os.path.join(pdf_dir, "*.pdf"))
    else:
        pdfs = sys.argv[1:]

    print("=" * 60)
    print("PDF复杂度分析")
    print("=" * 60)
    print()

    results = []
    for pdf_path in sorted(pdfs):
        result = analyze_pdf_from_file_path(pdf_path)
        results.append((pdf_path, result))

    print("=" * 60)
    print("汇总:")
    paddleocr_count = sum(1 for _, r in results if r['recommendation'] == 'paddleocr')
    pdfplumber_count = len(results) - paddleocr_count
    print(f"推荐使用PaddleOCR: {paddleocr_count} 个")
    print(f"推荐使用pdfplumber: {pdfplumber_count} 个")