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
                                page_parts.append(f"[表格 {t_idx + 1} on Page {page_num}]")
                                for row in table[:20]:
                                    page_parts.append(" | ".join(str(c).strip() for c in row if c))
                                if len(table) > 20:
                                    page_parts.append(f"... (共 {len(table)} 行)")
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
                    "text": text_content[:8000],
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

    if not chunks:
        return jsonify({"success": False, "error": {"code": "NO_CHUNKS", "message": "没有分块数据"}}), 400

    try:
        from models.vector_store import KnowledgeBase
        from config import DB_PATH, VECTOR_DIR
        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)

        # 转换为 KnowledgeBase 接受的格式
        if category == 'c_code':
            kb.add_c_code(chunks)
        else:
            kb.add_protocol_docs(chunks)

        return jsonify({
            "success": True,
            "data": {
                "count": len(chunks),
                "message": f"成功入库 {len(chunks)} 个分块"
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "INSERT_ERROR", "message": str(e)}}), 500
