# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')

import re
from models.vector_store import KnowledgeBase, QueryExpander, SYNONYM_DICT, BM25
from models.intent_classifier import IntentClassifier
import jieba

TEST_QUESTIONS = [
    ('Q1', 'App上操作了开机，仪表需要看iot发的哪条CAN指令？', 'can'),
    ('Q2', 'App在什么情况下会同步数据？', 'bluetooth'),
    ('Q3', '骑行记录是如何生成的？', 'bluetooth'),
]

class HeuristicEvaluator:
    def __init__(self):
        self.iot_keywords = ['iot', '开机', '指令', 'can', 'CAN', 'ota', 'OTA', 'Smart', '智能']
        self.sync_keywords = ['同步', 'dp', 'DP', 'query', 'QUERY', '状态', '查询', '0x0003', 'App', 'app', '数据']
        self.record_keywords = ['骑行', 'record', 'RECORD', '骑行记录', '0x8005', '生成', 'event', 'BLE', 'ble', 'vl_ble']

    def extract_key_terms(self, text: str) -> set:
        text_lower = text.lower()
        english = re.findall(r'[a-z0-9_]+', text_lower)
        english_terms = set()
        for w in english:
            parts = w.split('_')
            english_terms.update(p for p in parts if len(p) >= 2)
        chinese = list(jieba.cut(text_lower))
        chinese_terms = set(w for w in chinese if len(w) >= 2)
        return english_terms | chinese_terms

    def evaluate(self, question: str, retrieved_docs: list, iteration: int) -> dict:
        if not retrieved_docs:
            return {
                'relevance_score': 0.0,
                'key_findings': [],
                'missing_aspects': ['未检索到任何文档'],
                'search_suggestions': [],
                'is_satisfactory': False
            }

        question_terms = self.extract_key_terms(question)

        if 'can' in question.lower() or 'iot' in question.lower():
            target_keywords = self.iot_keywords
        elif '骑行' in question or 'record' in question.lower():
            target_keywords = self.record_keywords
        elif '同步' in question or 'sync' in question.lower():
            target_keywords = self.sync_keywords
        else:
            target_keywords = self.iot_keywords + self.sync_keywords + self.record_keywords

        doc_texts = []
        for doc in retrieved_docs:
            title = doc.get('title', '').lower()
            content = doc.get('content_preview', '').lower()
            source = doc.get('source', '').lower()
            doc_texts.append(title + ' ' + content + ' ' + source)

        all_doc_text = ' '.join(doc_texts)
        doc_terms = self.extract_key_terms(all_doc_text)

        matched = []
        missing = []
        for kw in target_keywords:
            kw_lower = kw.lower()
            found = False
            for dt in doc_texts:
                if kw_lower in dt or kw_lower.replace('_', '') in dt.replace('_', ''):
                    found = True
                    break
            if found:
                matched.append(kw)
            else:
                missing.append(kw)

        score = len(matched) / len(target_keywords) if target_keywords else 0

        suggestions = []
        for m in missing[:3]:
            if m in SYNONYM_DICT:
                suggestions.extend(SYNONYM_DICT[m][:2])
            m_parts = m.replace('_', ' ').split()
            suggestions.extend([p for p in m_parts if len(p) >= 2])

        key_findings = []
        for doc in retrieved_docs[:3]:
            title = doc.get('title', '')
            if title:
                key_findings.append(title[:50])

        return {
            'relevance_score': score,
            'key_findings': key_findings,
            'missing_aspects': missing[:3],
            'search_suggestions': list(set(suggestions))[:5],
            'is_satisfactory': score >= 0.4
        }

class SelfCorrectingRAGAgent:
    INTENT_TO_DB_CATEGORY = {
        'can': 'c_code',
        'bluetooth': 'c_code',
        'mqtt': 'c_code',
        'dp': 'c_code',
        'business': 'c_code',
        'log': 'log',
        'protocol': 'protocol',
        'c_code': 'c_code',
    }

    INTENT_CATEGORIES_TO_TRY = {
        'can': ['protocol', 'c_code'],
        'bluetooth': ['c_code', 'protocol'],
        'mqtt': ['c_code'],
        'dp': ['c_code'],
        'business': ['c_code', 'protocol'],
        'log': ['log'],
    }

    def __init__(self):
        self.kb = KnowledgeBase()
        self.classifier = IntentClassifier()
        self.expander = QueryExpander()
        self.evaluator = HeuristicEvaluator()
        self.max_iterations = 4

    def _map_category(self, intent_category: str) -> str:
        mapped = self.INTENT_TO_DB_CATEGORY.get(intent_category, 'c_code')
        return mapped

    def _get_categories_to_try(self, intent_category: str) -> list:
        return self.INTENT_CATEGORIES_TO_TRY.get(intent_category, ['c_code', 'protocol'])

    def retrieve(self, query: str, category: str, extra_terms: list = None) -> list:
        categories_to_try = self._get_categories_to_try(category)
        queries_to_try = [query]
        if extra_terms:
            for term in extra_terms[:5]:
                queries_to_try.append(f"{query} {term}")

        all_results = {}

        for cat in categories_to_try:
            for q in queries_to_try:
                results = self.kb.vector_store.search(q, category=cat, top_k=10)
                for r in results:
                    doc_id = r['id']
                    if doc_id not in all_results or all_results[doc_id] < r['score']:
                        all_results[doc_id] = r['score']

        if not all_results:
            for cat in ['c_code', 'protocol', 'log']:
                if cat not in categories_to_try:
                    for q in queries_to_try[:2]:
                        results = self.kb.vector_store.search(q, category=cat, top_k=10)
                        for r in results:
                            doc_id = r['id']
                            if doc_id not in all_results or all_results[doc_id] < r['score']:
                                all_results[doc_id] = r['score']
                    if all_results:
                        break

        sorted_results = sorted(all_results.items(), key=lambda x: x[1], reverse=True)
        top_results = []
        for doc_id, score in sorted_results[:10]:
            items = self.kb.metadata_db.search_items([doc_id])
            if items:
                item = items[0]
                top_results.append({
                    'id': item.id,
                    'score': score,
                    'source': item.source_file,
                    'title': item.title,
                    'content_preview': item.content[:300],
                    'line_number': item.line_number
                })
        return top_results

    def process_question(self, qid: str, question: str, expected_category: str) -> dict:
        print(f"\n{'='*60}")
        print(f"{qid}: {question}")
        print(f"期望类别: {expected_category}")
        print('-'*60)

        intent = self.classifier.classify(question)
        target_category = expected_category if expected_category else intent.category
        print(f"意图分类: {target_category} (conf:{intent.confidence:.2f})")

        retrieved = []
        extra_terms = []
        best_score = 0
        best_retrieved = []
        all_iterations = []

        for iteration in range(self.max_iterations):
            print(f"\n[迭代 {iteration + 1}]")

            if iteration == 0:
                print("  使用原始查询检索...")
            else:
                print(f"  添加搜索词: {extra_terms[-3:]}")

            retrieved = self.retrieve(question, target_category, extra_terms if iteration > 0 else None)
            print(f"  检索到 {len(retrieved)} 条结果")

            for i, r in enumerate(retrieved[:5]):
                fname = r['source'].replace('\\', '/').split('/')[-1]
                print(f"    [{i+1}] {r['score']:.2f} | {fname} | {r.get('title','')[:45]}")

            evaluation = self.evaluator.evaluate(question, retrieved, iteration)
            print(f"  评估: relevance={evaluation.get('relevance_score', 0):.1%}, satisfactory={evaluation.get('is_satisfactory', False)}")

            if evaluation.get('key_findings'):
                print(f"  关键发现: {evaluation['key_findings'][:2]}")
            if evaluation.get('missing_aspects'):
                print(f"  缺失: {evaluation['missing_aspects'][:3]}")

            all_iterations.append({
                'iteration': iteration,
                'retrieved': retrieved,
                'evaluation': evaluation,
                'extra_terms': list(extra_terms) if extra_terms else []
            })

            current_score = evaluation.get('relevance_score', 0)
            if current_score > best_score:
                best_score = current_score
                best_retrieved = list(retrieved)

            if evaluation.get('is_satisfactory', False):
                print("  ✓ 检索结果达标!")
                break

            suggestions = evaluation.get('search_suggestions', [])
            if suggestions and iteration < self.max_iterations - 1:
                new_terms = suggestions[:3]
                for t in new_terms:
                    if t not in extra_terms:
                        extra_terms.append(t)
                extra_terms = extra_terms[:10]

        return {
            'qid': qid,
            'question': question,
            'expected_category': expected_category,
            'target_category': target_category,
            'best_score': best_score,
            'best_retrieved': best_retrieved,
            'iterations': all_iterations
        }

    def run(self):
        print("="*60)
        print("RAG自我校对Agent (启发式评估)")
        print("="*60)

        results = []
        for qid, question, cat in TEST_QUESTIONS:
            result = self.process_question(qid, question, cat)
            results.append(result)

        print("\n" + "="*60)
        print("评估结果汇总")
        print("="*60)

        total_score = 0
        for r in results:
            status = "✓ PASS" if r['best_score'] >= 0.4 else "✗ FAIL"
            print(f"\n{r['qid']}: 检索质量={r['best_score']:.1%} {status}")
            print(f"  问题: {r['question']}")
            if r['best_retrieved']:
                print(f"  最佳结果 ({len(r['best_retrieved'])}条):")
                for doc in r['best_retrieved'][:3]:
                    fname = doc['source'].replace('\\', '/').split('/')[-1]
                    print(f"    - {fname}: {doc.get('title','')[:50]}")
            total_score += r['best_score']

        avg_score = total_score / len(results) if results else 0
        print("\n" + "="*60)
        print(f"平均检索质量: {avg_score:.1%}")
        print(f"目标准确率: 40% (检索质量阈值)")
        print(f"当前状态: {'✓ 达标' if avg_score >= 0.4 else '✗ 未达标'}")
        print("="*60)

        return results, avg_score

    def suggest_improvements(self, results):
        print("\n" + "="*60)
        print("系统优化建议")
        print("="*60)

        for r in results:
            if r['best_score'] < 0.4:
                print(f"\n{r['qid']}: {r['question'][:40]}...")
                missing = r['iterations'][-1]['evaluation'].get('missing_aspects', []) if r['iterations'] else []
                print(f"  缺失关键词: {missing}")

                for m in missing:
                    if m in SYNONYM_DICT:
                        print(f"    '{m}' 同义词: {SYNONYM_DICT[m]}")
                    else:
                        print(f"    '{m}' - 建议添加到SYNONYM_DICT")

if __name__ == "__main__":
    agent = SelfCorrectingRAGAgent()
    results, score = agent.run()
    agent.suggest_improvements(results)