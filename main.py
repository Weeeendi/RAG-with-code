import os
import sys
import hashlib

sys.path.insert(0, os.path.dirname(__file__))

from config import (
    MINIMAX_API_KEY, MINIMAX_BASE_URL,
    DB_PATH, VECTOR_DIR, SOURCE_DIRS
)
from models.vector_store import KnowledgeBase
from models.c_parser import CCodeParser
from models.protocol_parser import ProtocolDocParser
from models.log_parser import LogParser
from models.graph_extractor import CodeGraphExtractor
from models.enhanced_rag_engine import ReActRAGEngine


def compute_file_hash(file_path: str) -> str:
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def get_indexed_files() -> dict:
    indexed = {}
    for root, dirs, files in os.walk(SOURCE_DIRS["c_code"]):
        for f in files:
            if f.endswith(('.c', '.h')):
                indexed[os.path.join(root, f)] = 'c_code'
    for root, dirs, files in os.walk(SOURCE_DIRS["protocol_docs"]):
        for f in files:
            indexed[os.path.join(root, f)] = 'protocol'
    for root, dirs, files in os.walk(SOURCE_DIRS["logs"]):
        for f in files:
            if f.endswith(('.log', '.txt')):
                indexed[os.path.join(root, f)] = 'log'
    return indexed


def is_file_changed(file_path: str, file_hash: str) -> bool:
    vector_data = KnowledgeBase(DB_PATH, VECTOR_DIR).metadata_db.get_file_vectors(file_path)
    if not vector_data:
        return True
    import json
    data = json.loads(vector_data)
    return data.get('hash') != file_hash


def index_knowledge_base(force_reindex: bool = False):
    kb = KnowledgeBase(DB_PATH, VECTOR_DIR)

    print("索引知识库...")
    print("=" * 50)

    indexed_files = kb.metadata_db.get_all_files()
    indexed_files_normalized = {p.replace('\\', '/') for p in indexed_files}
    total_added = 0

    def get_rel_path(file_path: str) -> str:
        abs_path = os.path.abspath(file_path).replace('\\', '/')
        base_path = os.path.abspath('.').replace('\\', '/')
        if abs_path.startswith(base_path):
            return abs_path[len(base_path)+1:]
        return abs_path

    if os.path.exists(SOURCE_DIRS["c_code"]):
        c_code_files = []
        for root, dirs, files in os.walk(SOURCE_DIRS["c_code"]):
            c_code_files.extend([os.path.join(root, f) for f in files if f.endswith(('.c', '.h'))])

        new_or_changed = []
        unchanged = []
        for file_path in c_code_files:
            rel_path = get_rel_path(file_path)
            if force_reindex or rel_path not in indexed_files_normalized:
                new_or_changed.append(file_path)
            else:
                unchanged.append(file_path)

        print(f"C代码文件: {len(c_code_files)} 个 (新增/更新: {len(new_or_changed)}, 未变: {len(unchanged)})")

        if new_or_changed:
            # 使用图提取器处理所有C代码文件
            extractor = CodeGraphExtractor()
            all_nodes = []
            all_edges = []
            for i, file_path in enumerate(new_or_changed):
                sys.stdout.write(f"\r  处理进度: {i+1}/{len(new_or_changed)}")
                sys.stdout.flush()
                try:
                    graph_data = extractor.extract_from_file(file_path)
                    for node in graph_data['nodes']:
                        node['file'] = file_path.replace('\\', '/')
                    all_nodes.extend(graph_data['nodes'])
                    all_edges.extend(graph_data['edges'])
                except Exception as e:
                    print(f"\n  解析错误 {file_path}: {e}")
            if all_nodes:
                kb.add_graph_nodes(all_nodes, all_edges)
                total_added = len(all_nodes)
            print(f"\n  已索引 {total_added} 个代码图节点到数据库")

    if os.path.exists(SOURCE_DIRS["protocol_docs"]):
        doc_files = []
        for root, dirs, files in os.walk(SOURCE_DIRS["protocol_docs"]):
            doc_files.extend([os.path.join(root, f) for f in files])

        new_or_changed = []
        unchanged = []
        for file_path in doc_files:
            rel_path = get_rel_path(file_path)
            if force_reindex or rel_path not in indexed_files_normalized:
                new_or_changed.append(file_path)
            else:
                unchanged.append(file_path)

        print(f"协议文档: {len(doc_files)} 个 (新增/更新: {len(new_or_changed)}, 未变: {len(unchanged)})")

        if new_or_changed:
            doc_parser = ProtocolDocParser(SOURCE_DIRS["protocol_docs"])
            for i, file_path in enumerate(new_or_changed):
                sys.stdout.write(f"\r  处理进度: {i+1}/{len(new_or_changed)}")
                sys.stdout.flush()
                try:
                    doc_parser.parse_file(file_path)
                except Exception as e:
                    print(f"\n  跳过 {file_path}: {e}")
            docs = doc_parser.export_to_dict()
            if docs:
                kb.add_protocol_docs(docs)
            print(f"\n  已索引 {len(docs)} 个协议文档")
            total_added += len(docs)

    if os.path.exists(SOURCE_DIRS["logs"]):
        log_files = []
        for root, dirs, files in os.walk(SOURCE_DIRS["logs"]):
            log_files.extend([os.path.join(root, f) for f in files if f.endswith(('.log', '.txt'))])

        new_or_changed = []
        unchanged = []
        for file_path in log_files:
            rel_path = get_rel_path(file_path)
            if force_reindex or rel_path not in indexed_files_normalized:
                new_or_changed.append(file_path)
            else:
                unchanged.append(file_path)

        print(f"日志文件: {len(log_files)} 个 (新增/更新: {len(new_or_changed)}, 未变: {len(unchanged)})")

        if new_or_changed:
            log_parser = LogParser(SOURCE_DIRS["logs"])
            for i, file_path in enumerate(new_or_changed):
                sys.stdout.write(f"\r  处理进度: {i+1}/{len(new_or_changed)}")
                sys.stdout.flush()
                try:
                    log_parser.parse_file(file_path)
                except Exception as e:
                    print(f"\n  跳过 {file_path}: {e}")
            logs = log_parser.export_to_dict()
            if logs:
                kb.add_logs(logs)
            print(f"\n  已索引 {len(logs)} 条日志记录")
            total_added += len(logs)

    if total_added == 0:
        print("知识库已是最新，无需更新")
    else:
        print(f"共新增/更新 {total_added} 条记录")

    # 构建中文内容bigram索引和FTS5全文索引
    print("构建中文内容索引...")
    kb.metadata_db.build_content_bigram_index()
    kb.metadata_db.build_content_fts_index()

    print("=" * 50)
    print("索引完成! 启动交互模式...")
    return kb


def create_agent():
    kb = index_knowledge_base()
    agent = ReActRAGEngine(kb)
    return agent


def interactive_mode(agent):
    print("\n" + "=" * 50)
    print("物联网技术支持Agent - 交互模式")
    print("输入问题后按回车，输入 'quit' 退出")
    print("=" * 50 + "\n")

    history = []

    while True:
        try:
            question = input("问题: ").strip()
            if question.lower() in ['quit', 'exit', 'q']:
                print("退出程序")
                break
            if not question:
                continue

            print("  正在检索相关知识...", flush=True)
            result = agent.ask(question)

            print("\n" + "=" * 60)
            print("【Agent执行链路 - CoT推理过程】")
            print("=" * 60)

            for i, step in enumerate(result.get('history', [])):
                print(f"\n--- 第{i+1}轮 ---")

                if step.get('thought'):
                    thought_content = step['thought'].get('content', '') if isinstance(step['thought'], dict) else str(step['thought'])
                    if thought_content:
                        print(f"[Thought] {thought_content[:200]}")

                if step.get('query'):
                    print(f"[Action] search(\"{step['query']}\")")

                if step.get('results') is not None:
                    results_count = len(step['results']) if isinstance(step['results'], list) else 'N/A'
                    print(f"[Observation] 检索到 {results_count} 条结果")

                if step.get('tool'):
                    print(f"[Action] {step['tool']}({step.get('arguments', {})})")
                    if step.get('result', {}).get('success'):
                        data = step['result'].get('data', {})
                        if isinstance(data, dict) and 'count' in data:
                            print(f"[Observation] 结果数量: {data['count']}")
                        elif isinstance(data, list):
                            print(f"[Observation] 返回 {len(data)} 条数据")
                        else:
                            print(f"[Observation] 调用成功")
                    else:
                        error = step.get('result', {}).get('error', 'Unknown error')
                        print(f"[Observation] 错误: {error}")

                if step.get('intent_confirm'):
                    ic = step['intent_confirm']
                    if ic.get('success'):
                        print(f"\n【意图确认】")
                        if ic.get('intent'):
                            print(f"  识别意图: {ic['intent']}")
                        if ic.get('keywords'):
                            print(f"  建议检索词: {', '.join(ic['keywords'])}")
                        if ic.get('clarify'):
                            print(f"  澄清问题: {ic['clarify']}")

            print("\n" + "-" * 60)
            print(f"共进行 {result.get('iterations', 0)} 轮检索，共检索到 {result.get('total_results', 0)} 条结果")
            print(f"总耗时: {result.get('timing', {}).get('total', 0):.2f}s")
            print("-" * 60)

            # Show context summary
            ctx = result.get('context', '')
            if ctx and len(ctx) > 100:
                print(f"\n【检索上下文摘要】")
                print(ctx[:500] + "..." if len(ctx) > 500 else ctx)

            print(f"\n【最终回答】")
            print("-" * 40)
            print(result['answer'])
            print("-" * 40 + "\n")

            history.append({"role": "user", "content": question})
            history.append({"role": "assistant", "content": result['answer']})

        except KeyboardInterrupt:
            print("\n\n退出程序")
            break
        except Exception as e:
            print(f"处理问题时出错: {e}\n")




def create_app():
    from flask import Flask, request, jsonify
    from flask_cors import CORS

    app = Flask(__name__)
    CORS(app)

    agent = create_agent()

    @app.route('/api/health')
    def health():
        return jsonify({'status': 'ok'})

    @app.route('/api/qa', methods=['POST'])
    def qa():
        data = request.get_json()
        question = data.get('question', '').strip()
        if not question:
            return jsonify({'error': '问题不能为空'}), 400

        try:
            result = agent.ask(question)
            return jsonify({
                'question': result['question'],
                'answer': result['answer'],
                'history': result.get('history', []),
                'iterations': result.get('iterations', 0),
                'total_results': result.get('total_results', 0),
                'context': result.get('context', ''),
                'timing': result.get('timing', {})
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    # 注册实验室模块蓝图 (Data-to-Retrieval Loop)
    from labs.data_retrieval_loop.api.assets import assets_bp
    from labs.data_retrieval_loop.api.experiments import experiments_bp
    from labs.data_retrieval_loop.api.recall_test import recall_bp
    from labs.data_retrieval_loop.api.provenance import provenance_bp
    from labs.data_retrieval_loop.api.graph import graph_bp
    app.register_blueprint(assets_bp, url_prefix='/api/labs/assets')
    app.register_blueprint(experiments_bp, url_prefix='/api/labs/experiments')
    app.register_blueprint(recall_bp, url_prefix='/api/labs/recall')
    app.register_blueprint(provenance_bp, url_prefix='/api/labs/provenance')
    app.register_blueprint(graph_bp, url_prefix='/api/labs/graph')

    # 实验室 API
    @app.route('/api/labs/kbs', methods=['GET'])
    def list_labs_kbs():
        """获取知识库列表（基于文件系统）"""
        import os
        kb_root = "knowledge_base/raw"

        all_files = []
        indexed_files = set()
        try:
            import sqlite3
            conn = sqlite3.connect("data/metadata.db")
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT source_file FROM knowledge_items")
            for row in cursor.fetchall():
                if row[0]:
                    indexed_files.add(os.path.basename(row[0]))
            conn.close()
        except:
            pass

        for category in ['protocol_docs', 'c_code', 'logs']:
            full_path = os.path.join(kb_root, category)
            if os.path.isdir(full_path):
                for root, dirs, files in os.walk(full_path):
                    for name in files:
                        ext = os.path.splitext(name)[1].lower()
                        if ext in {'.pdf', '.md', '.txt', '.c', '.h', '.log'}:
                            all_files.append(name)

        total = len(all_files)
        indexed = len([f for f in all_files if f in indexed_files])

        return jsonify({'success': True, 'data': [{
            'kb_id': 'vehiclink-hardware',
            'name': '云迹硬件开发知识库',
            'doc_count': total,
            'indexed_count': indexed,
            'created_at': '2025-01-01'
        }]})

    @app.route('/api/labs/kbs/<kb_id>/docs', methods=['GET'])
    def list_labs_kb_docs(kb_id):
        """获取知识库的文档列表（基于文件系统+索引状态）"""
        import sqlite3
        import os
        kb_root = "knowledge_base/raw"
        docs = []

        category_map = {
            'protocol_docs': 'protocol',
            'c_code': 'c_code',
            'logs': 'log'
        }

        indexed_files = set()
        try:
            conn = sqlite3.connect("data/metadata.db")
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT source_file FROM knowledge_items")
            for row in cursor.fetchall():
                if row[0]:
                    indexed_files.add(os.path.basename(row[0]))
            conn.close()
        except:
            pass

        doc_summaries = {}
        try:
            conn = sqlite3.connect("data/labs.db")
            cursor = conn.cursor()
            cursor.execute("SELECT file_name, summary FROM asset_registry")
            for row in cursor.fetchall():
                doc_summaries[row[0]] = row[1]
            conn.close()
        except:
            pass

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

                        is_indexed = name in indexed_files
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

        return jsonify({'success': True, 'data': docs})

    @app.route('/api/labs/kbs/stats', methods=['GET'])
    def labs_kb_stats():
        """获取知识库统计信息（基于文件系统+索引状态）"""
        import sqlite3
        import os
        kb_root = "knowledge_base/raw"

        all_files = []
        indexed_files = set()
        try:
            conn = sqlite3.connect("data/metadata.db")
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT source_file FROM knowledge_items")
            for row in cursor.fetchall():
                if row[0]:
                    indexed_files.add(os.path.basename(row[0]))
            conn.close()
        except:
            pass

        for category in ['protocol_docs', 'c_code', 'logs']:
            full_path = os.path.join(kb_root, category)
            if os.path.isdir(full_path):
                for root, dirs, files in os.walk(full_path):
                    for name in files:
                        ext = os.path.splitext(name)[1].lower()
                        if ext in {'.pdf', '.md', '.txt', '.c', '.h', '.log'}:
                            all_files.append(name)

        total = len(all_files)
        indexed = len([f for f in all_files if f in indexed_files])

        return jsonify({
            'success': True,
            'data': {
                "total_assets": total,
                "indexed_assets": indexed,
                "doc_count": total,
                "chunk_count": indexed,
                "by_category": {
                    "protocol": len([f for f in all_files if f.endswith(('.pdf', '.md', '.txt'))]),
                    "c_code": len([f for f in all_files if f.endswith(('.c', '.h'))]),
                    "log": len([f for f in all_files if f.endswith('.log')])
                }
            }
        })

    @app.route('/api/labs/kbs', methods=['POST'])
    def create_labs_kb():
        """创建知识库"""
        data = request.get_json()
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'success': False, 'error': {'message': '知识库名称不能为空'}}), 400
        return jsonify({
            'success': True,
            'data': {
                'kb_id': 'vehiclink-hardware',
                'name': name,
                'business': data.get('business', ''),
                'description': data.get('description', ''),
                'doc_count': 0,
                'created_at': '2025-01-01'
            }
        }), 201

    @app.route('/api/labs/kbs/<kb_id>', methods=['PUT'])
    def update_labs_kb(kb_id):
        """更新知识库配置"""
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

    # 实验室Web测试页面
    @app.route('/labs')
    def labs_home():
        """知识库列表首页"""
        import os
        template_path = os.path.join(os.path.dirname(__file__), 'labs', 'data_retrieval_loop', 'templates', 'labs_home.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}

    @app.route('/labs/<kb_id>')
    def labs_kb_detail(kb_id):
        """知识库详情页（文档管理）"""
        import os
        template_path = os.path.join(os.path.dirname(__file__), 'labs', 'data_retrieval_loop', 'templates', 'labs_web.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}

    @app.route('/labs/<kb_id>/test')
    def labs_kb_test(kb_id):
        """知识库测试页（RAG控制台）"""
        import os
        template_path = os.path.join(os.path.dirname(__file__), 'labs', 'data_retrieval_loop', 'templates', 'labs_dashboard.html')
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/html; charset=utf-8'}

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='物联网技术支持Agent')
    parser.add_argument('--mode', choices=['interactive', 'api'], default='interactive',
                        help='运行模式: interactive=交互模式, api=REST API服务')
    parser.add_argument('--port', type=int, default=8000, help='API服务端口')
    parser.add_argument('--force-reindex', action='store_true',
                        help='强制全量重索引（清除现有c_code数据后重新处理）')
    args = parser.parse_args()

    if args.force_reindex:
        print("强制全量重索引模式 - 将清除现有c_code索引数据")
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM knowledge_items WHERE category = 'c_code'")
        cursor.execute("DELETE FROM knowledge_items WHERE type LIKE 'graph_%'")
        conn.commit()
        conn.close()
        print("已清除 c_code 和 graph 类别数据")

    if args.mode == 'api':
        print(f"启动REST API服务，端口: {args.port}")
        app = create_app()
        app.run(host='0.0.0.0', port=args.port, debug=False)
    else:
        print("=" * 50)
        print("物联网技术支持Agent - ReAct多轮迭代模式")
        print("=" * 50)
        agent = create_agent()
        interactive_mode(agent)