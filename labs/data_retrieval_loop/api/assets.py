"""
Asset Management API Routes
资产管理接口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from flask import Blueprint, request, jsonify
from labs.data_retrieval_loop.services.asset_service import (
    AssetService,
    DuplicateAssetError,
    UnsupportedFileTypeError,
    InvalidStateTransitionError,
    AssetNotFoundError
)

assets_bp = Blueprint('assets', __name__)


@assets_bp.route('/upload', methods=['POST'])
def upload_asset():
    """上传文件"""
    if 'file' not in request.files:
        return jsonify({
            "success": False,
            "error": {"code": "NO_FILE", "message": "未提供文件"}
        }), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({
            "success": False,
            "error": {"code": "NO_FILE", "message": "文件名为空"}
        }), 400

    tags = request.form.get('tags', '')
    tags = [t.strip() for t in tags.split(',') if t.strip()] if tags else []
    security_level = request.form.get('security_level', 'internal')
    owner = request.form.get('owner', '')
    notes = request.form.get('notes', '')

    try:
        service = AssetService()
        asset = service.upload_file(
            file_obj=file,
            tags=tags,
            security_level=security_level,
            owner=owner or None,
            notes=notes or None
        )

        return jsonify({
            "success": True,
            "data": {
                "asset_id": asset.asset_id,
                "file_name": asset.file_name,
                "file_size": asset.file_size,
                "md5_hash": asset.md5_hash,
                "status": asset.status,
                "category": asset.category,
                "tags": asset.tags,
                "created_at": asset.created_at
            }
        }), 201

    except DuplicateAssetError as e:
        return jsonify({
            "success": False,
            "error": {"code": "DUPLICATE_ASSET", "message": str(e), "asset_id": e.asset_id}
        }), 409

    except UnsupportedFileTypeError as e:
        return jsonify({
            "success": False,
            "error": {"code": "UNSUPPORTED_TYPE", "message": str(e)}
        }), 400


@assets_bp.route('', methods=['GET'])
def list_assets():
    """列出资产"""
    status = request.args.get('status')
    category = request.args.get('category')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    service = AssetService()
    assets = service.list_assets(status=status, category=category, limit=limit, offset=offset)

    return jsonify({
        "success": True,
        "data": [{
            "asset_id": a.asset_id,
            "file_name": a.file_name,
            "file_size": a.file_size,
            "status": a.status,
            "category": a.category,
            "tags": a.tags,
            "security_level": a.security_level,
            "created_at": a.created_at
        } for a in assets],
        "meta": {
            "limit": limit,
            "offset": offset
        }
    })


@assets_bp.route('/<asset_id>', methods=['GET'])
def get_asset(asset_id: str):
    """获取资产详情"""
    service = AssetService()
    asset = service.get_asset(asset_id)

    if not asset:
        return jsonify({
            "success": False,
            "error": {"code": "ASSET_NOT_FOUND", "message": f"资产不存在: {asset_id}"}
        }), 404

    return jsonify({
        "success": True,
        "data": {
            "asset_id": asset.asset_id,
            "file_name": asset.file_name,
            "file_path": asset.file_path,
            "file_size": asset.file_size,
            "md5_hash": asset.md5_hash,
            "sha256_hash": asset.sha256_hash,
            "status": asset.status,
            "category": asset.category,
            "tags": asset.tags,
            "security_level": asset.security_level,
            "owner": asset.owner,
            "notes": asset.notes,
            "error_message": asset.error_message,
            "retry_count": asset.retry_count,
            "created_at": asset.created_at,
            "updated_at": asset.updated_at
        }
    })


@assets_bp.route('/<asset_id>', methods=['PATCH'])
def update_asset(asset_id: str):
    """更新资产元数据"""
    data = request.get_json()

    if not data:
        return jsonify({
            "success": False,
            "error": {"code": "INVALID_REQUEST", "message": "请求体不能为空"}
        }), 400

    service = AssetService()

    try:
        asset = service.update_asset(
            asset_id=asset_id,
            file_name=data.get('file_name'),
            category=data.get('category'),
            tags=data.get('tags'),
            security_level=data.get('security_level'),
            owner=data.get('owner'),
            notes=data.get('notes')
        )

        return jsonify({
            "success": True,
            "data": {
                "asset_id": asset.asset_id,
                "file_name": asset.file_name,
                "category": asset.category,
                "tags": asset.tags,
                "security_level": asset.security_level,
                "owner": asset.owner,
                "notes": asset.notes,
                "updated_at": asset.updated_at
            }
        })
    except AssetNotFoundError as e:
        return jsonify({
            "success": False,
            "error": {"code": "ASSET_NOT_FOUND", "message": str(e)}
        }), 404


@assets_bp.route('/<asset_id>', methods=['DELETE'])
def delete_asset(asset_id: str):
    """删除资产"""
    force = request.args.get('force', 'false').lower() == 'true'

    service = AssetService()
    success = service.delete_asset(asset_id, force=force)

    if not success:
        return jsonify({
            "success": False,
            "error": {"code": "ASSET_NOT_FOUND", "message": f"资产不存在: {asset_id}"}
        }), 404

    return jsonify({
        "success": True,
        "message": "资产已删除"
    })


@assets_bp.route('/<asset_id>/status', methods=['GET'])
def get_asset_status(asset_id: str):
    """获取资产处理状态"""
    service = AssetService()
    status = service.get_asset_status(asset_id)

    if not status:
        return jsonify({
            "success": False,
            "error": {"code": "ASSET_NOT_FOUND", "message": f"资产不存在: {asset_id}"}
        }), 404

    return jsonify({
        "success": True,
        "data": status
    })


@assets_bp.route('/<asset_id>/reprocess', methods=['POST'])
def reprocess_asset(asset_id: str):
    """重新处理资产"""
    service = AssetService()

    try:
        task_id = service.reprocess_asset(asset_id)
        return jsonify({
            "success": True,
            "data": {"task_id": task_id, "asset_id": asset_id}
        })
    except AssetNotFoundError as e:
        return jsonify({
            "success": False,
            "error": {"code": "ASSET_NOT_FOUND", "message": str(e)}
        }), 404


@assets_bp.route('/<asset_id>/chunks', methods=['GET'])
def get_asset_chunks(asset_id: str):
    """获取资产的分块列表"""
    # TODO: 实现分块列表查询
    return jsonify({
        "success": False,
        "error": {"code": "NOT_IMPLEMENTED", "message": "暂未实现"}
    }), 501


@assets_bp.route('/parse', methods=['POST'])
def parse_file():
    """解析文件（预览用），复用 ToolExecutor，支持 OCR 回退和图片描述生成"""
    if 'file' not in request.files:
        return jsonify({
            "success": False,
            "error": {"code": "NO_FILE", "message": "未提供文件"}
        }), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({
            "success": False,
            "error": {"code": "NO_FILE", "message": "文件名为空"}
        }), 400

    # 支持 ?tool=pdf 指定工具，?tool=paddleocr 强制OCR
    tool_name = request.args.get('tool')
    force_ocr = request.args.get('force_ocr', 'false').lower() == 'true'
    if force_ocr:
        tool_name = 'paddleocr'

    import tempfile
    import uuid
    import re

    suffix = os.path.splitext(file.filename)[1]
    # 使用 D: 盘的临时目录，避免跨盘符问题
    temp_dir = r'D:\workspace\Agent\temp' if os.path.exists('D:\\') else tempfile.gettempdir()
    os.makedirs(temp_dir, exist_ok=True)
    tmp_path = os.path.join(temp_dir, f"{uuid.uuid4().hex}{suffix}")
    file.save(tmp_path)

    try:
        from models.tool_executor import ToolExecutor
        executor = ToolExecutor()
        result = executor.execute(tmp_path, tool_name=tool_name)

        if result.success:
            data = result.data
            stats = {
                "total_pages": 0,
                "total_tables": 0,
                "total_images": 0,
                "garble_rate": 0.0,
                "text_length": 0,
                "has_excel": False,
                "has_tables": False,
                "ocr_used": tool_name == 'paddleocr' or force_ocr,
                "image_descriptions": []
            }

            # 判断是 pdfplumber 格式还是 PaddleOCR 格式
            # pdfplumber: page (int), text/tables/images
            # PaddleOCR: page_num (int), markdown_text/content, 可能没有 tables/images
            is_pdfplumber_format = False
            if isinstance(data, list) and len(data) > 0:
                first = data[0]
                if isinstance(first, dict):
                    # 关键区分：pdfplumber 有 'page' 字段（纯整数），PaddleOCR 有 'page_num' 字段
                    if 'page' in first and isinstance(first.get('page'), int) and 'text' in first:
                        is_pdfplumber_format = True

            if isinstance(data, list) and is_pdfplumber_format:
                # pdfplumber 格式：每个元素是 page dict，有 text/tables/images 字段
                pages_text = []
                image_idx = 0
                for page in data[:20]:
                    if isinstance(page, dict):
                        page_num = page.get('page', '?')
                        text = page.get('text', '')
                        tables = page.get('tables', [])
                        images = page.get('images', [])

                        page_parts = []
                        if text:
                            page_parts.append(text)
                        if tables:
                            for t_idx, table in enumerate(tables):
                                page_parts.append(f"\n[表格 {t_idx + 1} on Page {page_num}]\n")
                                if table and len(table) > 0:
                                    # 格式化表格为Markdown格式
                                    max_cols = max(len(row) for row in table)
                                    header_row = table[0] if len(table) > 0 else []
                                    # 清理表头
                                    header_cells = [str(c).strip() if c else '' for c in header_row[:max_cols]]
                                    # 生成Markdown表头
                                    page_parts.append("| " + " | ".join(header_cells) + " |")
                                    # 生成分隔行
                                    page_parts.append("| " + " | ".join(['---'] * max_cols) + " |")
                                    # 生成数据行（最多显示20行）
                                    for row in table[1:min(21, len(table))]:
                                        cells = [str(c).strip() if c else '' for c in row[:max_cols]]
                                        # 补齐列数
                                        while len(cells) < max_cols:
                                            cells.append('')
                                        page_parts.append("| " + " | ".join(cells) + " |")
                                    if len(table) > 20:
                                        page_parts.append(f"\n... (共 {len(table)} 行)")
                                    else:
                                        page_parts.append("")
                        if images:
                            for img in images:
                                img_desc = _generate_image_description(img, image_idx, context=text[:500])
                                stats["image_descriptions"].append(img_desc)
                                page_parts.append(f"[图片 {image_idx + 1} on Page {page_num}]: {img_desc['description']}")
                                image_idx += 1

                        if page_parts:
                            pages_text.append(f"[Page {page_num}]\n" + "\n".join(page_parts))

                        stats["total_pages"] += 1
                        stats["total_tables"] += len(tables)
                        stats["total_images"] += len(images)
                        if tables:
                            stats["has_tables"] = True
                    elif isinstance(page, str):
                        pages_text.append(page)
                text_content = "\n\n".join(pages_text)
            elif isinstance(data, list):
                # PaddleOCR 格式：可能是 blocks 列表，每个有 page_num/markdown_text
                # 也可能是合并后的单个 block（page_num=0）
                pages_text = []
                image_idx = 0
                is_merged_content = False

                # 检查是否是合并的内容（第一个 block page_num=0 且有 content）
                if len(data) == 1 and isinstance(data[0], dict):
                    block = data[0]
                    if block.get('page_num') == 0 and block.get('content'):
                        # 这是合并后的内容
                        is_merged_content = True
                        content = block.get('content', '')
                        pages_text.append(content)
                        stats["total_pages"] = 1

                        # 处理图片
                        images = block.get('images', [])
                        if images:
                            for img in images:
                                img_desc = _generate_image_description(img, image_idx, context=content[:500])
                                stats["image_descriptions"].append(img_desc)
                                pages_text.append(f"\n[图片 {image_idx + 1}]: {img_desc['description']}")
                                image_idx += 1
                            stats["total_images"] = len(images)
                    else:
                        is_merged_content = False

                if not is_merged_content:
                    # 多个独立 blocks
                    for block in data[:20]:
                        if isinstance(block, dict):
                            page_num = block.get('page_num', block.get('page', '?'))
                            markdown_text = block.get('markdown_text', block.get('content', block.get('text', '')))
                            if markdown_text:
                                pages_text.append(f"[Page {page_num}]\n{markdown_text}")
                                stats["total_pages"] += 1
                            images = block.get('images', [])
                            if images:
                                for img in images:
                                    img_desc = _generate_image_description(img, len(stats["image_descriptions"]), context=markdown_text[:500])
                                    stats["image_descriptions"].append(img_desc)
                                    pages_text.append(f"\n[图片 {len(stats['image_descriptions'])}]: {img_desc['description']}")
                                stats["total_images"] += len(images)
                        elif isinstance(block, str):
                            pages_text.append(block)
                            stats["total_pages"] += 1
                text_content = "\n\n".join(pages_text)
            elif isinstance(data, dict):
                # Excel 格式：{sheet_name: rows}
                if 'sheet' in str(list(data.keys())[0]).lower() or 'Sheet' in str(list(data.keys())[0]):
                    stats["has_excel"] = True
                    parts = []
                    for sheet_name, rows in data.items():
                        parts.append(f"[Sheet: {sheet_name}]")
                        stats["total_tables"] += 1
                        for row in rows[:50]:
                            parts.append("\t".join(str(c) for c in row))
                    text_content = "\n".join(parts)
                else:
                    # 可能是 PaddleOCR 返回的单页 block
                    page_num = data.get('page_num', data.get('page', 1))
                    markdown_text = data.get('markdown_text', data.get('content', data.get('text', str(data))))
                    text_content = f"[Page {page_num}]\n{markdown_text}" if markdown_text else str(data)
                    stats["total_pages"] = 1
            elif isinstance(data, str):
                text_content = data
                stats["total_pages"] = 1
            else:
                text_content = str(data)
                stats["total_pages"] = 1

            # 计算乱码率
            if text_content:
                stats["text_length"] = len(text_content)
                garbled_patterns = [
                    r'[\x00-\x08\x0b-\x0c\x0e-\x1f]',  # 控制字符
                    r'[�]+',  # Unicode替换字符
                    r'(\?{2,})',   # 连续问号
                    r'([�]+)',     # 乱码方框
                ]
                garbled_count = 0
                for pattern in garbled_patterns:
                    garbled_count += len(re.findall(pattern, text_content))
                stats["garble_rate"] = round(garbled_count / len(text_content) * 100, 2) if garbled_count > 0 else 0.0

            # 如果乱码率>4%且未使用OCR，提示可切换
            warning = None
            if stats["garble_rate"] > 4 and not stats["ocr_used"]:
                warning = f"乱码率 {stats['garble_rate']}% 较高，建议使用 OCR 模式重新解析 (?force_ocr=true)"

            return jsonify({
                "success": True,
                "data": {
                    "text": text_content[:50000],
                    "file_name": file.filename,
                    "tool": tool_name or executor.registry.get_by_extension(suffix) or "auto",
                    "stats": stats,
                    "warning": warning
                }
            })
        else:
            return jsonify({
                "success": False,
                "error": {"code": "PARSE_ERROR", "message": result.error or "解析失败"}
            }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": {"code": "SERVER_ERROR", "message": str(e)}
        }), 500
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _generate_image_description(img_info: dict, idx: int, context: str = "") -> dict:
    """为图片生成描述标签，优先使用上下文推断，无效时使用尺寸描述"""
    desc = {
        "index": idx,
        "path": img_info.get('path', ''),
        "page": img_info.get('page', 0),
        "width": img_info.get('width', 0),
        "height": img_info.get('height', 0),
        "description": "",
        "tags": []
    }

    w, h = desc["width"], desc["height"]

    # 小图片（<100px）可能是图标，使用简单的尺寸描述
    if w > 0 and h > 0 and (w < 100 or h < 100):
        desc["description"] = f"图标/装饰图"
        desc["tags"] = ["图标", "装饰"]
        return desc

    # 基于上下文推断图片类型
    inferred = _infer_image_type_from_context(context, w, h)
    if inferred:
        desc["description"] = inferred["description"]
        desc["tags"] = inferred["tags"]
    else:
        # 使用尺寸描述
        ratio = w / h if h > 0 else 1
        size_type = "横版" if ratio > 1.2 else "竖版" if ratio < 0.8 else "方型"
        if w > 0 and h > 0:
            desc["description"] = f"图片{idx + 1} ({size_type}, {w}×{h})"
            desc["tags"] = [size_type, "插图"]
        else:
            desc["description"] = f"图片{idx + 1}"
            desc["tags"] = ["插图"]

    return desc


def _infer_image_type_from_context(context: str, w: int, h: int) -> dict:
    """根据上下文和尺寸推断图片类型"""
    if not context:
        return None

    context_lower = context.lower()

    # 根据常见关键词推断
    if any(kw in context_lower for kw in ['表格', 'table', '对照', '参数']):
        ratio = w / h if h > 0 else 1
        if ratio > 2:  # 宽屏可能是横向表格
            return {"description": "横向参数表格", "tags": ["表格", "参数", "横向"]}
        return {"description": "参数对照表", "tags": ["表格", "参数", "对照"]}

    if any(kw in context_lower for kw in ['流程', 'flow', '流程图']):
        return {"description": "流程图", "tags": ["流程图", "示意图", "流程"]}

    if any(kw in context_lower for kw in ['协议', 'protocol', '命令', 'cmd']):
        return {"description": "协议示意图", "tags": ["示意图", "协议", "命令"]}

    if any(kw in context_lower for kw in ['状态', 'state', '机', '状态机']):
        return {"description": "状态机图", "tags": ["状态机", "流程", "示意图"]}

    if any(kw in context_lower for kw in ['时序', 'sequence', '序列']):
        return {"description": "时序图", "tags": ["时序图", "序列", "示意图"]}

    if any(kw in context_lower for kw in ['帧', 'frame', '数据', 'packet']):
        return {"description": "数据帧格式图", "tags": ["数据帧", "格式", "示意图"]}

    if any(kw in context_lower for kw in ['连接', 'connect', 'session']):
        return {"description": "连接示意图", "tags": ["连接", "示意图", "流程"]}

    # 根据尺寸推断
    ratio = w / h if h > 0 else 1
    if 0.5 < ratio < 2:
        # 接近正方形
        if w > 400:
            return {"description": "方形示意图", "tags": ["示意图", "图示"]}
    elif ratio > 2:
        return {"description": "横幅图片", "tags": ["横幅", "横版"]}
    elif ratio < 0.5:
        return {"description": "竖幅图片", "tags": ["竖幅", "竖版"]}

    return None


@assets_bp.route('/retrieve', methods=['POST'])
def retrieve():
    """纯检索接口（不走LLM），用于检索调优测试"""
    data = request.get_json()
    query = data.get('query', '').strip()
    if not query:
        return jsonify({"success": False, "error": {"code": "MISSING_QUERY", "message": "查询词不能为空"}}), 400

    top_k = data.get('top_k', 10)
    threshold = data.get('threshold', 0.0)

    try:
        from models.vector_store import KnowledgeBase
        from config import DB_PATH, VECTOR_DIR
        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)
        items = kb.search(query, top_k=top_k)

        chunks = []
        for item in items:
            chunks.append({
                'id': item.id,
                'title': item.title,
                'content': item.content[:500] if item.content else '',
                'source': getattr(item, 'source_file', '') or '',
                'category': getattr(item, 'category', '') or ''
            })

        return jsonify({
            "success": True,
            "data": {
                "query": query,
                "count": len(chunks),
                "chunks": chunks
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "RETRIEVE_ERROR", "message": str(e)}}), 500


@assets_bp.route('/chunks', methods=['POST'])
def add_chunks():
    """将分块数据写入知识库"""
    data = request.get_json()
    category = data.get('category', 'protocol')
    chunks = data.get('chunks', [])
    file_name = data.get('file_name', '')
    file_content = data.get('file_content')  # 原始文件内容（base64）

    if not chunks:
        return jsonify({"success": False, "error": {"code": "NO_CHUNKS", "message": "没有分块数据"}}), 400

    try:
        import hashlib
        import base64
        from models.vector_store import KnowledgeBase
        from config import DB_PATH, VECTOR_DIR
        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)

        # 检查文件是否已存在（通过base64内容计算MD5）
        if file_content:
            try:
                content_bytes = base64.b64decode(file_content)
                md5_hash = hashlib.md5(content_bytes).hexdigest()
                # 检查metadata.db中是否已有此MD5
                import sqlite3
                conn = sqlite3.connect("data/metadata.db")
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM knowledge_items WHERE source_file LIKE ?", (f'%{file_name}',))
                exists = cursor.fetchone()[0] > 0
                conn.close()
                if exists:
                    return jsonify({
                        "success": False,
                        "error": {"code": "DUPLICATE_FILE", "message": f"文件 {file_name} 已入库，请勿重复添加"}
                    }), 409
            except Exception as e:
                print(f"MD5 check error: {e}")

        # 为每个chunk添加file_name到metadata
        import json
        for chunk in chunks:
            if 'metadata' not in chunk:
                chunk['metadata'] = {}
            if file_name:
                chunk['metadata']['file_name'] = file_name

        # 转换为 KnowledgeBase 接受的格式
        if category == 'c_code':
            # c_code uses graph extraction instead of chunking
            from models.graph_extractor import CodeGraphExtractor
            import base64
            if file_content:
                try:
                    content_bytes = base64.b64decode(file_content)
                    import tempfile
                    import os as os_module
                    # Write to temp file for extraction
                    with tempfile.NamedTemporaryFile(mode='wb', suffix=file_name, delete=False) as tmp:
                        tmp.write(content_bytes)
                        tmp_path = tmp.name
                    extractor = CodeGraphExtractor()
                    graph_data = extractor.extract_from_file(tmp_path)
                    os_module.unlink(tmp_path)
                    if graph_data['nodes']:
                        kb.add_graph_nodes(graph_data['nodes'], graph_data['edges'])
                        print(f"[Graph] Extracted {len(graph_data['nodes'])} nodes, {len(graph_data['edges'])} edges")
                    else:
                        print(f"[Graph] No graph nodes extracted from {file_name}")
                except Exception as e:
                    print(f"[Graph] Extraction error: {e}")
            else:
                kb.add_c_code(chunks)
        else:
            kb.add_protocol_docs(chunks)

        # 同步复制文件到knowledge_base/raw目录
        if file_content and file_name:
            try:
                content_bytes = base64.b64decode(file_content)
                kb_root = "knowledge_base/raw"
                dir_map = {'protocol': 'protocol_docs', 'c_code': 'c_code', 'log': 'logs'}
                target_dir = os.path.join(kb_root, dir_map.get(category, 'protocol_docs'))
                os.makedirs(target_dir, exist_ok=True)
                target_path = os.path.join(target_dir, file_name)
                with open(target_path, 'wb') as f:
                    f.write(content_bytes)
                print(f"[Sync] Copied {file_name} to {target_path}")
            except Exception as e:
                print(f"[Sync] Failed to copy {file_name}: {e}")

        # 保存文件记录到labs.db的asset_registry表
        if file_name:
            try:
                from config import LABS_DB_PATH
                conn = sqlite3.connect(LABS_DB_PATH)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO asset_registry (asset_id, file_name, file_path, status, summary, created_at, updated_at)
                    VALUES (?, ?, ?, 'indexed', NULL, datetime('now'), datetime('now'))
                """, (file_name, file_name, f'knowledge_base/raw/{category}/{file_name}'))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"Failed to save asset: {e}")

        # 触发异步摘要生成（不阻塞返回）
        import threading
        def async_generate_summary():
            _generate_summary_for_file(file_name, category, chunks)

        threading.Thread(target=async_generate_summary, daemon=True).start()

        return jsonify({
            "success": True,
            "data": {
                "count": len(chunks),
                "message": f"成功入库 {len(chunks)} 个分块，摘要生成中..."
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "INSERT_ERROR", "message": str(e)}}), 500


def _generate_summary_for_file(file_name, category, chunks):
    """异步为文件生成摘要"""
    import time
    time.sleep(2)  # 等待分块数据完全写入

    try:
        # 获取该文件的分块内容
        from config import DB_PATH
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT content FROM knowledge_items
            WHERE category = ? AND source_file LIKE ?
            ORDER BY id
            LIMIT 10
        """, (category, f'%{file_name}%'))
        chunk_contents = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()

        if not chunk_contents:
            return

        # 拼接前10个分块的内容用于生成摘要
        combined_text = '\n\n'.join(chunk_contents[:10])[:5000]

        # 调用LLM生成摘要
        import requests
        from config import MINIMAX_API_KEY

        url = "https://api.minimax.chat/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {MINIMAX_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "MiniMax-M2.7",
            "max_tokens": 300,
            "temperature": 0.3,
            "messages": [
                {"role": "user", "content": f"请为以下文档生成一个不超过200字的简短摘要，用于知识库检索辅助。只输出摘要内容，不要其他解释。\n\n文档内容：{combined_text}"}
            ]
        }

        session = requests.Session()
        session.trust_env = False
        response = session.post(url, headers=headers, json=payload, timeout=60)

        if response.status_code == 200:
            result = response.json()
            if result.get('choices') and result['choices'][0].get('message', {}).get('content'):
                summary = result['choices'][0]['message']['content'].strip()[:200]

                # 保存摘要到labs.db
                conn = sqlite3.connect("data/labs.db")
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE asset_registry SET summary = ?, updated_at = datetime('now')
                    WHERE file_name = ?
                """, (summary, file_name))
                conn.commit()
                conn.close()
                print(f"[Summary] Generated for {file_name}: {summary[:50]}...")

    except Exception as e:
        print(f"[Summary] Failed to generate summary for {file_name}: {e}")


def _trigger_summary_generation(file_name, db_category):
    """触发摘要生成（从metadata.db获取分块内容并生成摘要）"""
    try:
        from config import DB_PATH
        import sqlite3

        # 获取该文件的分块
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT content FROM knowledge_items
            WHERE category = ? AND source_file LIKE ?
            ORDER BY id
            LIMIT 10
        """, (db_category, f'%{file_name}%'))
        chunks = [{'content': row[0]} for row in cursor.fetchall() if row[0]]
        conn.close()

        if chunks:
            _generate_summary_for_file(file_name, db_category, chunks)
    except Exception as e:
        print(f"[Summary] Failed to trigger for {file_name}: {e}")


@assets_bp.route('/chunks/preview', methods=['POST'])
def preview_chunks():
    """预览分块效果"""
    data = request.get_json()
    text = data.get('text', '').strip()
    chunk_size = data.get('chunk_size', 800)
    overlap_ratio = data.get('overlap', 15) / 100.0
    mode = data.get('mode', 'fixed')

    if not text:
        return jsonify({"success": False, "error": {"code": "EMPTY_TEXT", "message": "文本不能为空"}}), 400

    overlap = int(chunk_size * overlap_ratio)

    has_tables = '[表格' in text
    table_info = []
    if has_tables:
        import re
        table_pattern = re.compile(r'\[表格 \d+ on Page \d+\](.*?)(?=\[表格|\[Page|Z$)', re.DOTALL)
        for match in table_pattern.finditer(text):
            table_content = match.group(0)
            if len(table_content) > 200:
                table_content = table_content[:200] + '...'
            table_info.append({"preview": table_content, "length": len(match.group(0))})

    chunks = []
    if mode == 'fixed':
        step = chunk_size - overlap
        for i in range(0, len(text), step):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunk_info = {"content": chunk, "chars": len(chunk), "index": len(chunks)}
                if '[表格' in chunk:
                    chunk_info["has_table"] = True
                chunks.append(chunk_info)
    elif mode == 'header':
        import re
        headers = [0]
        for match in re.finditer(r'\n#{1,3}\s+', text):
            headers.append(match.start())
        headers.append(len(text))

        for i in range(len(headers) - 1):
            chunk = text[headers[i]:headers[i+1]].strip()
            if chunk:
                chunk_info = {"content": chunk, "chars": len(chunk), "index": len(chunks)}
                if '[表格' in chunk:
                    chunk_info["has_table"] = True
                chunks.append(chunk_info)
    elif mode == 'semantic':
        import re
        semantic_chunks = []

        table_pattern = re.compile(r'\[表格 \d+ on Page \d+\].*?(?=\[表格|\[Page|\Z)', re.DOTALL)
        header_pattern = re.compile(r'^#{1,3}\s+.+$', re.MULTILINE)
        double_newline_pattern = re.compile(r'\n\n+')

        last_end = 0
        for match in table_pattern.finditer(text):
            if match.start() > last_end:
                section = text[last_end:match.start()]
                semantic_chunks.extend(_split_by_paragraphs(section, chunk_size, overlap))
            semantic_chunks.append({"content": match.group(0), "chars": len(match.group(0)), "index": len(semantic_chunks), "has_table": True})
            last_end = match.end()

        if last_end < len(text):
            semantic_chunks.extend(_split_by_paragraphs(text[last_end:], chunk_size, overlap))

        chunks = semantic_chunks
    else:
        step = chunk_size - overlap
        for i in range(0, len(text), step):
            chunk = text[i:i + chunk_size]
            if chunk.strip():
                chunk_info = {"content": chunk, "chars": len(chunk), "index": len(chunks)}
                if '[表格' in chunk:
                    chunk_info["has_table"] = True
                chunks.append(chunk_info)

    return jsonify({
        "success": True,
        "data": {
            "chunks": chunks[:20],
            "total": len(chunks),
            "chunk_size": chunk_size,
            "overlap": overlap,
            "table_count": len(table_info),
            "table_preview": table_info[:5]
        }
    })


def _split_by_paragraphs(text, chunk_size, overlap):
    """将文本按段落分块，保持段落完整性"""
    import re
    chunks = []
    double_newline_pattern = re.compile(r'\n\n+')
    paragraphs = double_newline_pattern.split(text)

    current_chunk = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += ("\n\n" if current_chunk else "") + para
        else:
            if current_chunk:
                chunks.append({"content": current_chunk, "chars": len(current_chunk), "index": len(chunks), "has_table": '[表格' in current_chunk})
            if len(para) > chunk_size:
                for i in range(0, len(para), chunk_size - overlap):
                    sub_chunk = para[i:i + chunk_size]
                    if sub_chunk.strip():
                        chunks.append({"content": sub_chunk, "chars": len(sub_chunk), "index": len(chunks), "has_table": '[表格' in sub_chunk})
                current_chunk = ""
            else:
                current_chunk = para

    if current_chunk:
        chunks.append({"content": current_chunk, "chars": len(current_chunk), "index": len(chunks), "has_table": '[表格' in current_chunk})

    return chunks

@assets_bp.route('/kb-tree', methods=['GET'])
def get_kb_tree():
    """获取知识库目录树（基于knowledge_base目录）"""
    import sqlite3
    from config import LABS_DB_PATH

    kb_root = "knowledge_base/raw"
    result = []

    # 忽略的目录模式（构建产物等）
    IGNORE_DIRS = {'build', 'CMakeFiles', 'cmake', 'node_modules', '.git', '__pycache__', 'GCC', 'MDK-ARM', 'Release', 'Debug', '.cmake'}

    # 有价值的文件扩展名
    VALUABLE_EXTS = {'.pdf', '.md', '.txt', '.c', '.h', '.log'}

    def _get_doc_recall_rate(doc_path):
        """从数据库查询文档的召回率"""
        try:
            conn = sqlite3.connect(LABS_DB_PATH)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT AVG(hit_rate) as avg_recall
                FROM recall_evaluations re
                JOIN ground_truth_questions gq ON re.qa_id = gq.qa_id
                WHERE gq.source = ? AND re.hit_rate IS NOT NULL
            """, (doc_path,))
            row = cursor.fetchone()
            conn.close()
            return round(row[0], 2) if row and row[0] else None
        except:
            return None

    def get_all_files(base_path, relative_path="", depth=0):
        """获取目录下所有文件（扁平化）"""
        items = []
        try:
            for name in sorted(os.listdir(base_path)):
                if name in IGNORE_DIRS:
                    continue

                full_path = os.path.join(base_path, name)
                rel_path = os.path.join(relative_path, name) if relative_path else name

                if os.path.isdir(full_path):
                    if depth < 2:
                        items.extend(get_all_files(full_path, rel_path, depth + 1))
                else:
                    ext = os.path.splitext(name)[1].lower()
                    if ext in VALUABLE_EXTS:
                        try:
                            file_size = os.path.getsize(full_path)
                            recall_rate = _get_doc_recall_rate(rel_path)
                            items.append({
                                "name": name,
                                "path": rel_path,
                                "type": "file",
                                "ext": ext,
                                "size": file_size,
                                "recall_rate": recall_rate
                            })
                        except:
                            pass
        except PermissionError:
            pass
        return items

    def get_folders_only(base_path, relative_path="", depth=0, max_depth=2):
        """只获取文件夹结构，不获取文件"""
        items = []
        try:
            for name in sorted(os.listdir(base_path)):
                if name in IGNORE_DIRS:
                    continue

                full_path = os.path.join(base_path, name)
                rel_path = os.path.join(relative_path, name) if relative_path else name

                if os.path.isdir(full_path):
                    children = []
                    if depth < max_depth:
                        children = get_folders_only(full_path, rel_path, depth + 1, max_depth)
                    items.append({
                        "name": name,
                        "path": rel_path,
                        "type": "folder",
                        "children": children
                    })
        except PermissionError:
            pass
        return items

    # 处理 protocol_docs - 显示文件列表
    protocol_path = os.path.join(kb_root, 'protocol_docs')
    if os.path.isdir(protocol_path):
        files = get_all_files(protocol_path, 'protocol_docs')
        if files:
            result.append({
                "name": "protocol_docs",
                "path": "protocol_docs",
                "type": "folder",
                "displayName": "📋 协议文档",
                "children": files
            })

    # 处理 c_code - 只显示项目名称（第一层目录），不可展开
    c_code_path = os.path.join(kb_root, 'c_code')
    if os.path.isdir(c_code_path):
        # 获取c_code下的第一层子目录作为代码项目
        code_projects = []
        for name in os.listdir(c_code_path):
            full_path = os.path.join(c_code_path, name)
            if os.path.isdir(full_path):
                code_projects.append({
                    "name": name,
                    "path": os.path.join('c_code', name),
                    "type": "code_project",
                    "displayName": name,
                    "children": []  # 不可展开
                })
        if code_projects:
            result.append({
                "name": "c_code",
                "path": "c_code",
                "type": "folder",
                "displayName": "💻 C代码",
                "children": code_projects
            })

    # 处理 logs
    logs_path = os.path.join(kb_root, 'logs')
    if os.path.isdir(logs_path):
        files = get_all_files(logs_path, 'logs')
        if files:
            result.append({
                "name": "logs",
                "path": "logs",
                "type": "folder",
                "displayName": "📝 日志",
                "children": files
            })

    # 如果没有扫描到内容
    if not result:
        result = [
            {"name": "protocol_docs", "path": "protocol_docs", "type": "folder", "displayName": "📋 协议文档", "children": []},
            {"name": "c_code", "path": "c_code", "type": "folder", "displayName": "💻 C代码", "children": []},
            {"name": "logs", "path": "logs", "type": "folder", "displayName": "📝 日志", "children": []}
        ]

    return jsonify({
        "success": True,
        "data": result
    })


@assets_bp.route('/kb-stats', methods=['GET'])
def get_kb_stats():
    """获取知识库统计信息"""
    import sqlite3
    from config import LABS_DB_PATH, VECTOR_DIR

    stats = {
        "total_docs": 0,
        "total_chunks": 0,
        "indexed_docs": 0,
        "categories": {}
    }

    # 统计knowledge_base目录
    kb_root = "knowledge_base/raw"
    for category in ['protocol_docs', 'c_code', 'logs']:
        full_path = os.path.join(kb_root, category)
        if os.path.isdir(full_path):
            count = 0
            for root, dirs, files in os.walk(full_path):
                count += len([f for f in files if f.endswith(('.pdf', '.txt', '.md', '.c', '.h', '.log'))])
            stats["categories"][category] = count
            stats["total_docs"] += count

    # 统计已索引的文档
    try:
        conn = sqlite3.connect(LABS_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM asset_registry WHERE status = 'indexed'")
        stats["indexed_docs"] = cursor.fetchone()[0]
        conn.close()
    except:
        pass

    # 统计分块数
    try:
        conn = sqlite3.connect("data/metadata.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks")
        stats["total_chunks"] = cursor.fetchone()[0]
        conn.close()
    except:
        pass

    return jsonify({
        "success": True,
        "data": stats
    })


@assets_bp.route('/kbs', methods=['GET'])
def list_knowledge_bases():
    """获取知识库列表"""
    import sqlite3
    from config import LABS_DB_PATH

    # 统计protocol_docs中的文档数量
    kb_root = "knowledge_base/raw/protocol_docs"
    doc_count = 0
    if os.path.isdir(kb_root):
        for name in os.listdir(kb_root):
            ext = os.path.splitext(name)[1].lower()
            if ext in {'.pdf', '.md', '.txt'}:
                doc_count += 1

    return jsonify({
        "success": True,
        "data": [{
            "kb_id": "vehiclink-hardware",
            "name": "云迹硬件开发知识库",
            "doc_count": doc_count,
            "created_at": "2025-01-01"
        }]
    })


@assets_bp.route('/kbs/<kb_id>', methods=['PUT'])
def update_kb(kb_id):
    """更新知识库"""
    data = request.get_json()
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'success': False, 'error': {'message': '知识库名称不能为空'}}), 400
    return jsonify({
        'success': True,
        'data': {
            'kb_id': kb_id,
            'name': name,
            'business': data.get('business', ''),
            'description': data.get('description', '')
        }
    })


@assets_bp.route('/kbs/<kb_id>/docs', methods=['GET'])
def list_kb_docs(kb_id):
    """获取知识库的文档列表"""
    import sqlite3
    kb_root = "knowledge_base/raw"
    docs = []

    # 类别映射：文件夹名 -> 数据库category值
    category_map = {
        'protocol_docs': 'protocol',
        'c_code': 'c_code',
        'logs': 'log'
    }

    # 获取每个类别是否有已索引的数据
    indexed_categories = set()
    try:
        conn = sqlite3.connect("data/metadata.db")
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM knowledge_items")
        for row in cursor.fetchall():
            indexed_categories.add(row[0])
        conn.close()
    except:
        pass

    # 获取每个文档的摘要（从labs.db）
    doc_summaries = {}
    doc_needs_summary = []  # 记录需要生成摘要的文档
    try:
        conn = sqlite3.connect("data/labs.db")
        cursor = conn.cursor()
        cursor.execute("SELECT file_name, summary FROM asset_registry")
        for row in cursor.fetchall():
            doc_summaries[row[0]] = row[1]  # row[1]可能是None
        conn.close()
    except:
        pass

    for category in ['protocol_docs', 'c_code', 'logs']:
        full_path = os.path.join(kb_root, category)
        db_category = category_map.get(category, category)

        # 该类别是否已索引
        is_category_indexed = db_category in indexed_categories

        if os.path.isdir(full_path):
            for name in sorted(os.listdir(full_path)):
                full_file_path = os.path.join(full_path, name)
                is_dir = os.path.isdir(full_file_path)
                ext = os.path.splitext(name)[1].lower()

                # c_code类别：只显示第一层目录（代码项目），不显示文件
                if category == 'c_code':
                    if is_dir:
                        docs.append({
                            "name": name,
                            "path": os.path.join(category, name),
                            "category": category,
                            "size": 0,
                            "type": "folder",
                            "status": "indexed" if is_category_indexed else "pending",
                            "summary": ""
                        })
                    continue

                # 其他类别：只处理特定扩展名的文件
                if ext in {'.pdf', '.md', '.txt', '.c', '.h', '.log'}:
                    try:
                        size = os.path.getsize(full_file_path)
                    except:
                        size = 0

                    # 如果该类别已索引，所有文件都标记为已索引
                    is_indexed = is_category_indexed

                    # 获取该文档的摘要
                    summary = doc_summaries.get(name, '') or ''

                    docs.append({
                        "name": name,
                        "path": os.path.join(category, name),
                        "category": category,
                        "size": size,
                        "type": ext,
                        "status": "indexed" if is_indexed else "pending",
                        "summary": summary if summary else ''
                    })

                    # 如果文档已索引但没有摘要，触发异步生成
                    if is_indexed and not summary:
                        doc_needs_summary.append((name, db_category))

    # 触发异步摘要生成（不阻塞返回）
    if doc_needs_summary:
        import threading
        def async_generate_missing_summaries():
            import time
            time.sleep(3)  # 等待前端加载完成
            for file_name, db_category in doc_needs_summary:
                _trigger_summary_generation(file_name, db_category)

        threading.Thread(target=async_generate_missing_summaries, daemon=True).start()

    return jsonify({
        "success": True,
        "data": docs
    })


@assets_bp.route('/doc-content', methods=['POST'])
def get_doc_content():
    """获取文档内容（从已索引的分块中获取）"""
    data = request.get_json()
    path = data.get('path', '').strip()

    if not path:
        return jsonify({"success": False, "error": {"code": "MISSING_PATH", "message": "路径不能为空"}}), 400

    # 从路径中提取文件名和类别
    path_parts = path.replace('\\', '/').split('/')
    file_name = path_parts[-1] if path_parts else ''
    category = path_parts[0] if len(path_parts) > 1 else ''

    try:
        conn = sqlite3.connect("data/metadata.db")
        cursor = conn.cursor()

        # 查询该文档的分块内容 - 使用类别+文件名模糊匹配
        cursor.execute("""
            SELECT content FROM knowledge_items
            WHERE (source_file LIKE ? AND source_file LIKE ?)
               OR (source_file LIKE ? AND source_file LIKE ?)
            ORDER BY id
            LIMIT 50
        """, (f"%{category}%", f"%{file_name[:20]}%", f"%{category}%", f"%{file_name}%"))

        chunks = cursor.fetchall()
        conn.close()

        if not chunks:
            return jsonify({
                "success": True,
                "data": {"content": "", "message": "文档未入库"}
            })

        # 拼接分块内容
        full_content = "\n\n".join([c[0] for c in chunks if c[0]])

        return jsonify({
            "success": True,
            "data": {
                "content": full_content,
                "chunk_count": len(chunks),
                "total_chars": len(full_content)
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "DB_ERROR", "message": str(e)}}), 500


@assets_bp.route('/doc', methods=['DELETE'])
def delete_doc():
    """删除知识库文档（按路径）"""
    data = request.get_json()
    path = data.get('path', '').strip()

    if not path:
        return jsonify({"success": False, "error": {"code": "MISSING_PATH", "message": "路径不能为空"}}), 400

    path_parts = path.replace('\\', '/').split('/')
    file_name = path_parts[-1] if path_parts else ''
    category = path_parts[0] if len(path_parts) > 1 else ''

    try:
        conn = sqlite3.connect("data/metadata.db")
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM knowledge_items WHERE source_file LIKE ? LIMIT 1", (f"%{file_name}%",))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "error": {"code": "FILE_NOT_FOUND", "message": f"文档未入库: {file_name}"}}), 404

        cursor.execute("DELETE FROM knowledge_items WHERE source_file LIKE ?", (f"%{file_name}%",))
        deleted_knowledge = cursor.rowcount

        cursor.execute("DELETE FROM asset_chunk_mapping WHERE asset_id IN (SELECT asset_id FROM asset_registry WHERE file_name LIKE ?)", (f"%{file_name}%",))
        deleted_mapping = cursor.rowcount

        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "data": {
                "file_name": file_name,
                "deleted_chunks": deleted_knowledge,
                "deleted_mapping": deleted_mapping
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "DB_ERROR", "message": str(e)}}), 500


def _calculate_garble_ratio(blocks: list) -> float:
    """计算块的乱码比例 - 检测半角符号、CJK兼容性和 radicals"""
    if not blocks:
        return 0.0

    garbled_count = 0
    for b in blocks:
        content = b.get('content', '')
        if not content:
            continue

        char_count = len(content)
        if char_count == 0:
            continue

        halfwidth_marks = sum(1 for c in content if '\ufe00' <= c <= '\ufe0f')
        compatibility_forms = sum(1 for c in content if '\uf900' <= c <= '\ufaff')
        cjk_radicals = sum(1 for c in content if '\u2e80' <= c <= '\u2eff')
        replacement_char = content.count('\ufffd')
        halfwidth_letters = sum(1 for c in content if '\uff61' <= c <= '\uff64')

        problematic = halfwidth_marks + compatibility_forms + cjk_radicals + replacement_char + halfwidth_letters
        garbled_ratio = problematic / char_count
        if garbled_ratio > 0.15:
            garbled_count += 1

    return garbled_count / len(blocks)


@assets_bp.route('/rebuild', methods=['POST'])
def rebuild_knowledge_base():
    """重建知识库（全链路解析、分块、导入）"""
    data = request.get_json() or {}
    chunk_size = data.get('chunk_size', 1500)
    clear_first = data.get('clear_first', True)

    try:
        import os
        import sys
        import sqlite3
        import base64
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

        from models.protocol_parser import ProtocolDocParser
        from models.tool_executor import ToolExecutor
        from models.c_parser import CCodeParser
        from models.log_parser import LogParser
        from models.vector_store import KnowledgeBase
        from models.graph_extractor import CodeGraphExtractor
        from config import DB_PATH, VECTOR_DIR

        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)
        tool_executor = ToolExecutor()

        if clear_first:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM knowledge_items")
            conn.commit()
            conn.close()

            try:
                labs_conn = sqlite3.connect("data/labs.db")
                labs_cursor = labs_conn.cursor()
                try:
                    labs_cursor.execute("DELETE FROM asset_chunk_mapping")
                except:
                    pass
                labs_conn.commit()
                labs_conn.close()
            except:
                pass

            print("[Rebuild] Cleared existing knowledge_items")

        kb_root = "knowledge_base/raw"
        categories = {
            'protocol_docs': ('protocol', ProtocolDocParser),
            'c_code': ('c_code', CCodeParser),
            'logs': ('log', LogParser)
        }

        total_chunks = 0
        processed_files = 0
        errors = []

        for category_dir, (category, parser_class) in categories.items():
            category_path = os.path.join(kb_root, category_dir)
            if not os.path.isdir(category_path):
                continue

            files = []
            for name in os.listdir(category_path):
                ext = os.path.splitext(name)[1].lower()
                if category_dir == 'c_code' and ext in {'.c', '.h'}:
                    files.append(name)
                elif category_dir == 'protocol_docs' and ext in {'.pdf', '.md', '.txt'}:
                    files.append(name)
                elif category_dir == 'logs' and ext in {'.log', '.txt'}:
                    files.append(name)

            for file_name in files:
                try:
                    file_path = os.path.join(category_path, file_name)
                    print(f"[Rebuild] Processing {category_dir}/{file_name}")

                    if parser_class:
                        ext = os.path.splitext(file_name)[1].lower()
                        blocks = []

                        if category == 'protocol' and ext == '.pdf':
                            parser = parser_class(category_path)
                            parser.parse_file(file_path)
                            blocks = parser.export_to_dict()

                            if blocks:
                                garble_ratio = self._calculate_garble_ratio(blocks)
                                if garble_ratio > 0.3:
                                    print(f"  -> Detected garbled content ({garble_ratio*100:.0f}%), re-parsing with OCR...")
                                    blocks = []
                                    pd_result = tool_executor._parse_pdf_paddleocr(file_path)
                                    if pd_result.success and isinstance(pd_result.data, list):
                                        for page in pd_result.data:
                                            if isinstance(page, dict) and page.get('content'):
                                                text = page['content']
                                                page_blocks = parser._extract_blocks(parser.text_cleaner.clean(text), file_path, "document")
                                                blocks.extend(page_blocks)
                                    print(f"  -> OCR yielded {len(blocks)} blocks")
                        else:
                            parser = parser_class(category_path)
                            parser.parse_file(file_path)
                            blocks = parser.export_to_dict()

                        if blocks:
                            for block in blocks:
                                block['metadata'] = block.get('metadata', {})
                                block['metadata']['file_name'] = file_name

                            if category == 'protocol':
                                kb.add_protocol_docs(blocks)
                            elif category == 'c_code':
                                # c_code uses graph extraction instead of chunking
                                extractor = CodeGraphExtractor()
                                graph_data = extractor.extract_from_file(file_path)
                                if graph_data['nodes']:
                                    kb.add_graph_nodes(graph_data['nodes'], graph_data['edges'])
                                    total_chunks += len(graph_data['nodes'])
                                processed_files += 1
                                print(f"  -> {len(graph_data['nodes'])} graph nodes, {len(graph_data['edges'])} edges")
                            elif category == 'log':
                                kb.add_logs(blocks)

                except Exception as e:
                    errors.append(f"{file_name}: {str(e)}")
                    print(f"  -> Error: {e}")

        return jsonify({
            "success": True,
            "data": {
                "processed_files": processed_files,
                "total_chunks": total_chunks,
                "errors": errors if errors else None
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "REBUILD_ERROR", "message": str(e)}}), 500
