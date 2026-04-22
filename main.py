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
from models.rag_engine import FAQAgent
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
            parser = CCodeParser(SOURCE_DIRS["c_code"])
            for i, file_path in enumerate(new_or_changed):
                sys.stdout.write(f"\r  处理进度: {i+1}/{len(new_or_changed)}")
                sys.stdout.flush()
                try:
                    parser.parse_file(file_path)
                except Exception as e:
                    print(f"\n  解析错误 {file_path}: {e}")
            c_dicts = parser.export_to_dict()
            if c_dicts:
                kb.add_c_code(c_dicts)
                total_added = len(c_dicts)
            print(f"\n  已索引 {total_added} 个代码块到数据库")

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

    # 构建中文内容bigram索引
    print("构建中文内容索引...")
    kb.metadata_db.build_content_bigram_index()

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


def manage_mode(agent: FAQAgent):
    print("\n" + "=" * 50)
    print("知识库管理 - Feedback审核模式")
    print("=" * 50 + "\n")

    while True:
        try:
            print("\n选项:")
            print("  1. 查看未处理的反馈")
            print("  2. 修正知识库条目")
            print("  3. 删除错误条目")
            print("  4. 查看相关知识")
            print("  5. 返回/退出")
            choice = input("\n请选择操作 (1-5): ").strip()

            if choice == '5':
                break

            if choice == '1':
                feedback_list = agent.get_unresolved_feedback()
                if not feedback_list:
                    print("\n暂无未处理的反馈")
                    continue
                print(f"\n共有 {len(feedback_list)} 条未处理反馈:\n")
                for fb in feedback_list:
                    print(f"[ID:{fb['id']}] 问题: {fb['question'][:50]}...")
                    print(f"       原回答: {fb['answer'][:80]}...")
                    print(f"       时间: {fb['created_at']}")
                    print("-" * 40)

            elif choice == '2':
                fb_id = input("请输入要修正的feedback ID: ").strip()
                try:
                    fb_id = int(fb_id)
                except:
                    print("无效的ID")
                    continue

                related = agent.rag.kb.find_related_items(
                    next((f['question'] for f in agent.get_unresolved_feedback() if f['id'] == fb_id), ''),
                    limit=1
                )
                if related:
                    print(f"\n当前知识库内容:\n{related[0].content[:200]}...")
                    print(f"来源: {related[0].source_file}:{related[0].line_number}")

                new_content = input("\n请输入修正后的内容: ").strip()
                if not new_content:
                    print("内容不能为空")
                    continue

                if agent.fix_knowledge_from_feedback(fb_id, new_content):
                    print("知识库已更新")
                else:
                    print("修正失败")

            elif choice == '3':
                fb_id = input("请输入要删除的feedback ID: ").strip()
                try:
                    fb_id = int(fb_id)
                except:
                    print("无效的ID")
                    continue

                confirm = input("确认删除相关知识库条目? (y/n): ").strip().lower()
                if confirm == 'y':
                    if agent.delete_wrong_knowledge(fb_id):
                        print("已删除")
                    else:
                        print("删除失败")

            elif choice == '4':
                keyword = input("请输入关键词搜索: ").strip()
                if not keyword:
                    continue
                related = agent.rag.kb.find_related_items(keyword, limit=5)
                if not related:
                    print("未找到相关内容")
                else:
                    for i, item in enumerate(related):
                        print(f"\n[{i+1}] {item.title}")
                        print(f"    来源: {item.source_file}:{item.line_number}")
                        print(f"    内容: {item.content[:150]}...")

        except KeyboardInterrupt:
            print("\n退出管理模式")
            break
        except Exception as e:
            print(f"操作出错: {e}")


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
                'iterations': result.get('history', []),
                'timing': result.get('timing', {})
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return app


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='物联网技术支持Agent')
    parser.add_argument('--mode', choices=['interactive', 'api', 'manage'], default='interactive',
                        help='运行模式: interactive=交互模式, api=REST API服务, manage=知识库管理')
    parser.add_argument('--port', type=int, default=8000, help='API服务端口')
    args = parser.parse_args()

    if args.mode == 'api':
        print(f"启动REST API服务，端口: {args.port}")
        app = create_app()
        app.run(host='0.0.0.0', port=args.port, debug=False)
    elif args.mode == 'manage':
        print("=" * 50)
        print("物联网技术支持Agent - 知识库管理模式")
        print("=" * 50)
        agent = create_agent()
        manage_mode(agent)
    else:
        print("=" * 50)
        print("物联网技术支持Agent - ReAct多轮迭代模式")
        print("=" * 50)
        agent = create_agent()
        interactive_mode(agent)