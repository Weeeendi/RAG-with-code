"""
Graph API Routes
图关系查询接口
"""
import sys
import os
import json
import hashlib
import threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from flask import Blueprint, request, jsonify
from models.graph_extractor import CodeGraphExtractor, DPProtocolRelationExtractor
from models.vector_store import KnowledgeBase
from config import DB_PATH, VECTOR_DIR, GRAPH_DIR

graph_bp = Blueprint('graph', __name__)

GRAPH_BUILD_STATUS = {
    "running": False,
    "progress": 0,
    "total": 0,
    "message": "",
    "last_update": None
}


def _background_build(source_dir, force):
    """后台构建图关系"""
    global GRAPH_BUILD_STATUS
    try:
        GRAPH_BUILD_STATUS["running"] = True
        GRAPH_BUILD_STATUS["progress"] = 0
        GRAPH_BUILD_STATUS["message"] = "正在提取代码图关系..."

        extractor = CodeGraphExtractor(source_dir)
        result = extractor.process_directory(force=force)

        os.makedirs(GRAPH_DIR, exist_ok=True)
        for file_path, graph in extractor.graphs.items():
            safe_name = hashlib.md5(file_path.encode()).hexdigest()[:12]
            output_path = os.path.join(GRAPH_DIR, f"{safe_name}.json")
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(graph, f, ensure_ascii=False, indent=2)

        GRAPH_BUILD_STATUS["message"] = f"正在导入 {result['total_nodes']} 个图节点..."
        GRAPH_BUILD_STATUS["total"] = result['total_nodes']

        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)
        batch_size = 200
        processed = 0

        for file_path, graph in list(extractor.graphs.items()):
            if graph['nodes']:
                kb.add_graph_nodes(graph['nodes'], graph['edges'], batch_size=batch_size)
                processed += len(graph['nodes'])
                GRAPH_BUILD_STATUS["progress"] = processed
                GRAPH_BUILD_STATUS["message"] = f"已导入 {processed}/{result['total_nodes']} 个节点"

        GRAPH_BUILD_STATUS["running"] = False
        GRAPH_BUILD_STATUS["message"] = f"完成! 共 {result['total_nodes']} 节点, {result['total_edges']} 边"
        GRAPH_BUILD_STATUS["progress"] = result['total_nodes']

    except Exception as e:
        GRAPH_BUILD_STATUS["running"] = False
        GRAPH_BUILD_STATUS["message"] = f"错误: {str(e)}"


@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """构建代码图关系（后台异步执行）"""
    global GRAPH_BUILD_STATUS

    if GRAPH_BUILD_STATUS["running"]:
        return jsonify({
            "success": False,
            "error": {"code": "BUILD_IN_PROGRESS", "message": "图构建正在进行中"}
        }), 409

    data = request.get_json() or {}
    source_dir = data.get('source_dir', 'knowledge_base/raw/c_code')
    force = data.get('force', False)

    thread = threading.Thread(target=_background_build, args=(source_dir, force))
    thread.daemon = True
    thread.start()

    return jsonify({
        "success": True,
        "data": {
            "message": "图构建已启动，请在 /graph/status 查看进度"
        }
    })


@graph_bp.route('/status', methods=['GET'])
def graph_status():
    """获取图构建状态"""
    return jsonify({
        "success": True,
        "data": GRAPH_BUILD_STATUS
    })


@graph_bp.route('/dp_can_relations', methods=['GET'])
def get_dp_can_relations():
    """获取DP和CAN协议的映射关系"""
    try:
        extractor = DPProtocolRelationExtractor()
        relations = extractor.process_all_protocols()

        return jsonify({
            "success": True,
            "data": {
                "total_relations": len(relations),
                "relations": relations[:100]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "RELATION_ERROR", "message": str(e)}}), 500


@graph_bp.route('/callers/<func_name>', methods=['GET'])
def get_callers(func_name):
    """获取调用指定函数的的所有函数"""
    try:
        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)
        callers = kb.get_callers(func_name)

        return jsonify({
            "success": True,
            "data": {
                "function": func_name,
                "callers": [{"id": c.id, "title": c.title, "source": c.source_file} for c in callers]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "QUERY_ERROR", "message": str(e)}}), 500


@graph_bp.route('/callees/<func_name>', methods=['GET'])
def get_callees(func_name):
    """获取指定函数调用的所有函数"""
    try:
        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)
        callees = kb.get_callees(func_name)

        return jsonify({
            "success": True,
            "data": {
                "function": func_name,
                "callees": [{"id": c.id, "title": c.title, "source": c.source_file} for c in callees]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "QUERY_ERROR", "message": str(e)}}), 500


@graph_bp.route('/search', methods=['GET'])
def search_graph():
    """搜索图节点"""
    query = request.args.get('q', '')
    top_k = int(request.args.get('top_k', 5))

    if not query:
        return jsonify({"success": False, "error": {"code": "MISSING_QUERY", "message": "查询词不能为空"}}), 400

    try:
        kb = KnowledgeBase(DB_PATH, VECTOR_DIR)
        results = kb.search_graph(query, top_k=top_k)

        return jsonify({
            "success": True,
            "data": {
                "query": query,
                "results": [{
                    "id": r.id,
                    "title": r.title,
                    "type": r.type,
                    "source_file": r.source_file,
                    "line_number": r.line_number,
                    "content_preview": r.content[:200] if r.content else '',
                    "edges": r.metadata.get('edges', []) if r.metadata else []
                } for r in results]
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "SEARCH_ERROR", "message": str(e)}}), 500


@graph_bp.route('/stats', methods=['GET'])
def graph_stats():
    """获取图统计信息"""
    try:
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM knowledge_items WHERE category = 'graph'")
        node_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT source_file) FROM knowledge_items WHERE category = 'graph'")
        file_count = cursor.fetchone()[0]

        conn.close()

        return jsonify({
            "success": True,
            "data": {
                "total_nodes": node_count,
                "indexed_files": file_count,
                "graph_dir": GRAPH_DIR,
                "build_status": GRAPH_BUILD_STATUS
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": {"code": "STATS_ERROR", "message": str(e)}}), 500