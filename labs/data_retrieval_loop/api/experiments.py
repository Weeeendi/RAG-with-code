"""
Experiment Configuration API Routes
实验配置接口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from flask import Blueprint, request, jsonify
from labs.data_retrieval_loop.services.experiment_service import (
    ExperimentService,
    InvalidChunkSizeError,
    InvalidOverlapRatioError,
    InvalidSplitterTypeError,
    ConfigNotFoundError,
    ConfigAlreadyActiveError,
    ConfigCannotDeleteError
)

experiments_bp = Blueprint('experiments', __name__)


@experiments_bp.route('', methods=['POST'])
def create_experiment():
    """创建实验配置"""
    data = request.get_json()

    config_name = data.get('config_name')
    if not config_name:
        return jsonify({
            "success": False,
            "error": {"code": "MISSING_NAME", "message": "配置名称不能为空"}
        }), 400

    chunk_size = data.get('chunk_size', 800)
    overlap_ratio = data.get('overlap_ratio', 0.15)
    splitter_type = data.get('splitter_type', 'smart')
    description = data.get('description')
    asset_ids = data.get('asset_ids', [])
    is_shadow = data.get('is_shadow', False)

    try:
        service = ExperimentService()
        config = service.create_config(
            config_name=config_name,
            chunk_size=chunk_size,
            overlap_ratio=overlap_ratio,
            splitter_type=splitter_type,
            description=description,
            asset_ids=asset_ids,
            is_shadow=is_shadow
        )

        return jsonify({
            "success": True,
            "data": {
                "config_id": config.config_id,
                "config_name": config.config_name,
                "chunk_size": config.chunk_size,
                "overlap_ratio": config.overlap_ratio,
                "splitter_type": config.splitter_type,
                "index_name": config.index_name,
                "is_shadow": config.is_shadow,
                "status": config.status,
                "created_at": config.created_at
            }
        }), 201

    except (InvalidChunkSizeError, InvalidOverlapRatioError, InvalidSplitterTypeError) as e:
        return jsonify({
            "success": False,
            "error": {"code": "INVALID_PARAM", "message": str(e)}
        }), 400


@experiments_bp.route('', methods=['GET'])
def list_experiments():
    """列出实验配置"""
    status = request.args.get('status')
    is_shadow = request.args.get('is_shadow')
    if is_shadow is not None:
        is_shadow = is_shadow.lower() == 'true'
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    service = ExperimentService()
    configs = service.list_configs(status=status, is_shadow=is_shadow, limit=limit, offset=offset)

    return jsonify({
        "success": True,
        "data": [{
            "config_id": c.config_id,
            "config_name": c.config_name,
            "chunk_size": c.chunk_size,
            "overlap_ratio": c.overlap_ratio,
            "splitter_type": c.splitter_type,
            "is_shadow": c.is_shadow,
            "status": c.status,
            "created_at": c.created_at
        } for c in configs],
        "meta": {"limit": limit, "offset": offset}
    })


@experiments_bp.route('/<config_id>', methods=['GET'])
def get_experiment(config_id: str):
    """获取实验配置详情"""
    service = ExperimentService()
    config = service.get_config(config_id)

    if not config:
        return jsonify({
            "success": False,
            "error": {"code": "CONFIG_NOT_FOUND", "message": f"配置不存在: {config_id}"}
        }), 404

    return jsonify({
        "success": True,
        "data": {
            "config_id": config.config_id,
            "config_name": config.config_name,
            "description": config.description,
            "chunk_size": config.chunk_size,
            "overlap_ratio": config.overlap_ratio,
            "splitter_type": config.splitter_type,
            "vector_weight_bm25": config.vector_weight_bm25,
            "vector_weight_tfidf": config.vector_weight_tfidf,
            "vector_weight_faiss": config.vector_weight_faiss,
            "asset_ids": config.asset_ids,
            "index_name": config.index_name,
            "is_shadow": config.is_shadow,
            "status": config.status,
            "created_at": config.created_at,
            "updated_at": config.updated_at
        }
    })


@experiments_bp.route('/<config_id>', methods=['PUT'])
def update_experiment(config_id: str):
    """更新实验配置"""
    data = request.get_json()

    service = ExperimentService()
    config = service.update_config(config_id, **data)

    if not config:
        return jsonify({
            "success": False,
            "error": {"code": "CONFIG_NOT_FOUND", "message": f"配置不存在: {config_id}"}
        }), 404

    return jsonify({
        "success": True,
        "data": {
            "config_id": config.config_id,
            "config_name": config.config_name,
            "status": config.status,
            "updated_at": config.updated_at
        }
    })


@experiments_bp.route('/<config_id>', methods=['DELETE'])
def delete_experiment(config_id: str):
    """删除实验配置"""
    force = request.args.get('force', 'false').lower() == 'true'

    service = ExperimentService()
    try:
        service.delete_config(config_id, force=force)
        return jsonify({
            "success": True,
            "message": "配置已删除"
        })
    except ConfigCannotDeleteError as e:
        return jsonify({
            "success": False,
            "error": {"code": "CONFIG_CANNOT_DELETE", "message": str(e)}
        }), 400


@experiments_bp.route('/<config_id>/unarchive', methods=['POST'])
def unarchive_experiment(config_id: str):
    """解除归档状态"""
    service = ExperimentService()
    try:
        config = service.unarchive_config(config_id)
        return jsonify({
            "success": True,
            "data": {
                "config_id": config.config_id,
                "status": config.status
            }
        })
    except ConfigNotFoundError as e:
        return jsonify({
            "success": False,
            "error": {"code": "CONFIG_NOT_FOUND", "message": str(e)}
        }), 404


@experiments_bp.route('/<config_id>/activate', methods=['POST'])
def activate_experiment(config_id: str):
    """激活配置（创建影子索引）"""
    service = ExperimentService()

    try:
        index_version_id = service.activate_config(config_id)
        return jsonify({
            "success": True,
            "data": {
                "config_id": config_id,
                "index_version_id": index_version_id,
                "message": "配置已激活，影子索引已创建"
            }
        })
    except ConfigNotFoundError as e:
        return jsonify({
            "success": False,
            "error": {"code": "CONFIG_NOT_FOUND", "message": str(e)}
        }), 404
    except ConfigAlreadyActiveError as e:
        return jsonify({
            "success": False,
            "error": {"code": "CONFIG_ALREADY_ACTIVE", "message": str(e)}
        }), 409


@experiments_bp.route('/compare', methods=['POST'])
def compare_experiments():
    """对比多个配置"""
    data = request.get_json()
    config_ids = data.get('config_ids', [])

    if len(config_ids) < 2:
        return jsonify({
            "success": False,
            "error": {"code": "INVALID_PARAM", "message": "需要至少2个配置进行对比"}
        }), 400

    service = ExperimentService()
    report = service.compare_configs(config_ids)

    return jsonify({
        "success": True,
        "data": report
    })
