"""
Provenance API Routes
溯源可视化接口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from flask import Blueprint, request, jsonify
from labs.data_retrieval_loop.services.provenance_service import ProvenanceService

provenance_bp = Blueprint('provenance', __name__)


@provenance_bp.route('/chunk/<chunk_id>', methods=['GET'])
def get_chunk_provenance(chunk_id: str):
    """获取分块溯源信息"""
    service = ProvenanceService()
    provenance = service.get_chunk_provenance(chunk_id)

    if not provenance:
        return jsonify({
            "success": False,
            "error": {"code": "CHUNK_NOT_FOUND", "message": f"分块不存在: {chunk_id}"}
        }), 404

    return jsonify({
        "success": True,
        "data": {
            "mapping_id": provenance.mapping_id,
            "chunk_id": provenance.chunk_id,
            "asset_id": provenance.asset_id,
            "file_name": provenance.file_name,
            "file_path": provenance.file_path,
            "chunk_index": provenance.chunk_index,
            "page_number": provenance.page_number,
            "line_start": provenance.line_start,
            "line_end": provenance.line_end,
            "bounding_box": provenance.bounding_box,
            "chunk_preview": provenance.chunk_preview
        }
    })


@provenance_bp.route('/asset/<asset_id>/chunks', methods=['GET'])
def get_asset_chunks(asset_id: str):
    """获取资产的所有分块"""
    service = ProvenanceService()
    chunks = service.get_asset_chunks(asset_id)

    return jsonify({
        "success": True,
        "data": [{
            "chunk_id": c.chunk_id,
            "chunk_index": c.chunk_index,
            "page_number": c.page_number,
            "line_start": c.line_start,
            "line_end": c.line_end,
            "chunk_preview": c.chunk_preview
        } for c in chunks]
    })


@provenance_bp.route('/asset/<asset_id>/pdf_preview', methods=['GET'])
def get_pdf_preview(asset_id: str):
    """获取PDF预览坐标"""
    page_number = request.args.get('page', type=int)

    service = ProvenanceService()
    result = service.get_pdf_preview_coords(asset_id, page_number)

    if "error" in result:
        return jsonify({
            "success": False,
            "error": {"code": "ASSET_NOT_FOUND", "message": result["error"]}
        }), 404

    return jsonify({
        "success": True,
        "data": result
    })


@provenance_bp.route('/asset/<asset_id>/chunks', methods=['POST'])
def create_chunk_mapping(asset_id: str):
    """创建分块溯源记录"""
    data = request.get_json()

    chunk_id = data.get('chunk_id')
    if not chunk_id:
        return jsonify({
            "success": False,
            "error": {"code": "MISSING_CHUNK_ID", "message": "chunk_id 不能为空"}
        }), 400

    chunk_index = data.get('chunk_index', 0)
    page_number = data.get('page_number')
    line_start = data.get('line_start')
    line_end = data.get('line_end')
    bounding_box = data.get('bounding_box')
    chunk_preview = data.get('chunk_preview')

    service = ProvenanceService()
    provenance = service.create_chunk_mapping(
        asset_id=asset_id,
        chunk_id=chunk_id,
        chunk_index=chunk_index,
        page_number=page_number,
        line_start=line_start,
        line_end=line_end,
        bounding_box=bounding_box,
        chunk_preview=chunk_preview
    )

    return jsonify({
        "success": True,
        "data": {
            "mapping_id": provenance.mapping_id,
            "chunk_id": provenance.chunk_id,
            "asset_id": provenance.asset_id,
            "page_number": provenance.page_number,
            "created": True
        }
    }), 201


@provenance_bp.route('/search', methods=['GET'])
def search_with_provenance():
    """搜索分块并返回溯源"""
    query = request.args.get('query', '')
    top_k = request.args.get('top_k', 5, type=int)
    asset_id = request.args.get('asset_id')

    service = ProvenanceService()
    results = service.search_with_provenance(
        query=query,
        top_k=top_k,
        asset_id=asset_id
    )

    return jsonify({
        "success": True,
        "data": results
    })
