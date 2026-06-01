"""
Recall Test API Routes
召回测试接口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from flask import Blueprint, request, jsonify
from labs.data_retrieval_loop.services.recall_test_service import RecallTestService

recall_bp = Blueprint('recall', __name__)


# ========== Ground Truth Sets ==========

@recall_bp.route('/sets', methods=['POST'])
def create_question_set():
    """创建问题集"""
    data = request.get_json()

    set_name = data.get('set_name')
    if not set_name:
        return jsonify({
            "success": False,
            "error": {"code": "MISSING_NAME", "message": "问题集名称不能为空"}
        }), 400

    service = RecallTestService()
    gt_set = service.create_question_set(
        set_name=set_name,
        description=data.get('description'),
        category=data.get('category'),
        created_by=data.get('created_by')
    )

    return jsonify({
        "success": True,
        "data": {
            "set_id": gt_set.set_id,
            "set_name": gt_set.set_name,
            "description": gt_set.description,
            "category": gt_set.category,
            "question_count": gt_set.question_count,
            "created_at": gt_set.created_at
        }
    }), 201


@recall_bp.route('/sets', methods=['GET'])
def list_question_sets():
    """列出问题集"""
    category = request.args.get('category')
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)

    service = RecallTestService()
    sets = service.list_question_sets(category=category, limit=limit, offset=offset)

    return jsonify({
        "success": True,
        "data": [{
            "set_id": s.set_id,
            "set_name": s.set_name,
            "description": s.description,
            "category": s.category,
            "question_count": s.question_count,
            "created_at": s.created_at
        } for s in sets],
        "meta": {"limit": limit, "offset": offset}
    })


@recall_bp.route('/sets/<set_id>', methods=['GET'])
def get_question_set(set_id: str):
    """获取问题集详情"""
    service = RecallTestService()
    gt_set = service.get_question_set(set_id)

    if not gt_set:
        return jsonify({
            "success": False,
            "error": {"code": "SET_NOT_FOUND", "message": f"问题集不存在: {set_id}"}
        }), 404

    # 获取问题列表
    questions = service.get_questions_by_set(set_id)

    return jsonify({
        "success": True,
        "data": {
            "set_id": gt_set.set_id,
            "set_name": gt_set.set_name,
            "description": gt_set.description,
            "category": gt_set.category,
            "question_count": gt_set.question_count,
            "questions": [{
                "qa_id": q.qa_id,
                "question": q.question,
                "difficulty": q.difficulty,
                "relevant_chunk_ids": q.relevant_chunk_ids
            } for q in questions],
            "created_at": gt_set.created_at
        }
    })


# ========== Ground Truth Questions ==========

@recall_bp.route('/sets/<set_id>/questions', methods=['POST'])
def add_question(set_id: str):
    """添加问题到问题集"""
    data = request.get_json()

    question = data.get('question')
    if not question:
        return jsonify({
            "success": False,
            "error": {"code": "MISSING_QUESTION", "message": "问题内容不能为空"}
        }), 400

    service = RecallTestService()

    # 检查问题集是否存在
    gt_set = service.get_question_set(set_id)
    if not gt_set:
        return jsonify({
            "success": False,
            "error": {"code": "SET_NOT_FOUND", "message": f"问题集不存在: {set_id}"}
        }), 404

    gt_question = service.add_question(
        set_id=set_id,
        question=question,
        relevant_chunk_ids=data.get('relevant_chunk_ids', []),
        difficulty=data.get('difficulty', 3),
        expected_answer=data.get('expected_answer'),
        source=data.get('source', 'manual')
    )

    return jsonify({
        "success": True,
        "data": {
            "qa_id": gt_question.qa_id,
            "question": gt_question.question,
            "difficulty": gt_question.difficulty,
            "created_at": gt_question.created_at
        }
    }), 201


# ========== Evaluation ==========

@recall_bp.route('/sets/<set_id>/evaluate', methods=['POST'])
def evaluate_set(set_id: str):
    """执行召回评估"""
    data = request.get_json()

    config_id = data.get('config_id')
    if not config_id:
        return jsonify({
            "success": False,
            "error": {"code": "MISSING_CONFIG", "message": "config_id 不能为空"}
        }), 400

    k_values = data.get('k_values', [1, 3, 5, 10])
    retrieved_results = data.get('retrieved_results', [])

    service = RecallTestService()

    # 检查问题集是否存在
    gt_set = service.get_question_set(set_id)
    if not gt_set:
        return jsonify({
            "success": False,
            "error": {"code": "SET_NOT_FOUND", "message": f"问题集不存在: {set_id}"}
        }), 404

    # 执行评估
    results = service.evaluate_config(
        config_id=config_id,
        set_id=set_id,
        k_values=k_values,
        retrieved_results=retrieved_results
    )

    # 获取聚合指标
    metrics = service.get_aggregate_metrics(config_id)

    return jsonify({
        "success": True,
        "data": {
            "set_id": set_id,
            "config_id": config_id,
            "eval_count": len(results),
            "metrics": metrics,
            "results": [{
                "eval_id": r.eval_id,
                "question": r.question,
                "hit_rate": r.hit_rate,
                "mrr": r.mrr,
                "score_distribution": r.score_distribution
            } for r in results[:10]]  # 最多返回10条详细结果
        }
    })


@recall_bp.route('/evaluations/<eval_id>', methods=['GET'])
def get_evaluation(eval_id: str):
    """获取评估结果详情"""
    service = RecallTestService()
    results = service.get_evaluation_results()

    result = next((r for r in results if r.eval_id == eval_id), None)
    if not result:
        return jsonify({
            "success": False,
            "error": {"code": "EVAL_NOT_FOUND", "message": f"评估结果不存在: {eval_id}"}
        }), 404

    return jsonify({
        "success": True,
        "data": {
            "eval_id": result.eval_id,
            "config_id": result.config_id,
            "set_id": result.set_id,
            "question": result.question,
            "retrieved_chunk_ids": result.retrieved_chunk_ids,
            "expected_chunk_ids": result.expected_chunk_ids,
            "hits": result.hits,
            "hit_rate": result.hit_rate,
            "mrr": result.mrr,
            "score_distribution": result.score_distribution,
            "evaluated_at": result.evaluated_at
        }
    })


@recall_bp.route('/evaluations/<eval_id>/distribution', methods=['GET'])
def get_score_distribution(eval_id: str):
    """获取分数分布"""
    service = RecallTestService()
    results = service.get_evaluation_results()

    result = next((r for r in results if r.eval_id == eval_id), None)
    if not result:
        return jsonify({
            "success": False,
            "error": {"code": "EVAL_NOT_FOUND", "message": f"评估结果不存在: {eval_id}"}
        }), 404

    return jsonify({
        "success": True,
        "data": {
            "eval_id": result.eval_id,
            "question": result.question,
            "score_distribution": result.score_distribution
        }
    })
