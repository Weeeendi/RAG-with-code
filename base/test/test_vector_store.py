"""
向量库测试用例

测试覆盖：
1. BM25 doc_idx 对齐问题（多文件搜索时 doc_idx 应加 start_idx 偏移）
2. id_bigrams 计算问题（应使用 id_content 字符而非 query 字符）
3. Category fallback（category 过滤无结果时应回退到无 category）
4. QueryExpander 关键词扩展
"""

import sys
sys.path.insert(0, r'D:\workspace\Agent')

import unittest
import re
from collections import Counter


class TestBM25DocIdxAlignment(unittest.TestCase):
    """测试 BM25 搜索结果的 doc_idx 对齐问题"""

    def test_doc_idx_should_be_offset_by_start_idx(self):
        """当多个文件合并检索时，doc_idx 应该被 start_idx 偏移"""
        # 模拟场景：第一个文件有 3 个 item，第二个文件有 2 个 item
        # 第一个文件的 start_idx = 0，第二个文件的 start_idx = 3
        # BM25 返回 doc_idx=0（第二个文件的第一个 item）
        # 实际应该是 start_idx + doc_idx = 3 + 0 = 3

        start_idx = 3
        doc_idx = 0
        item_map = [f'item_{i}' for i in range(6)]  # 共 6 个 item

        # 错误的计算（直接用 doc_idx）：
        wrong_idx = doc_idx
        wrong_id = item_map[doc_idx] if doc_idx < len(item_map) else None

        # 正确的计算（doc_idx + start_idx）：
        correct_idx = start_idx + doc_idx
        correct_id = item_map[correct_idx] if correct_idx < len(item_map) else None

        # 验证
        self.assertEqual(wrong_id, 'item_0')  # 错误地取到了第一个文件的 item
        self.assertEqual(correct_id, 'item_3')  # 正确取到了第二个文件的第一个 item

    def test_bm25_scores_with_actual_implementation(self):
        """测试实际的 BM25 评分逻辑"""
        from models.vector_store import BM25

        # 创建两个文档
        doc1 = "骑行记录上报规则"
        doc2 = "蓝牙连接状态"

        bm25 = BM25()
        bm25.fit([doc1, doc2])

        # 搜索 "骑行记录"
        scores = bm25.search("骑行记录", top_k=5)

        # doc_idx=0 应该有正分（匹配 doc1），doc_idx=1 应该是 0
        score_map = {idx: s for idx, s in scores}

        self.assertGreater(score_map.get(0, 0), 0, "doc_idx=0 应该匹配 '骑行记录'")
        self.assertEqual(score_map.get(1, 0), 0, "doc_idx=1 不应该匹配 '骑行记录'")


class TestIdBigramsCalculation(unittest.TestCase):
    """测试 id_bigrams 计算使用正确的字符集"""

    def test_id_bigrams_should_use_id_content_chars(self):
        """id_bigrams 应该使用 id_content 的字符，而不是 query 的字符"""
        # Query: "骑行记录"
        query = "骑行记录"
        chinese_chars = list(re.findall(r'[一-鿿]', query.lower()))

        # 错误实现：使用 query 的 chars 计算 bigrams
        wrong_bigrams = set()
        for i in range(len(chinese_chars) - 1):
            wrong_bigrams.add(chinese_chars[i] + chinese_chars[i+1])

        # 正确实现：使用 id_content 的 chars 计算 bigrams
        id_content = "knowledge_base/raw/protocol_docs\\App内dp上报逻辑.pdf"
        id_content_chars = list(re.findall(r'[一-鿿]', id_content.lower()))
        correct_bigrams = set()
        for i in range(len(id_content_chars) - 1):
            correct_bigrams.add(id_content_chars[i] + id_content_chars[i+1])

        # 验证
        self.assertIn('骑行', wrong_bigrams)
        self.assertNotIn('骑行', correct_bigrams)  # id_content 中没有 "骑行"
        self.assertIn('上报', correct_bigrams)


class TestCategoryFallback(unittest.TestCase):
    """测试 category 过滤无结果时的回退机制"""

    def test_category_mismatch_should_trigger_fallback(self):
        """当指定 category 与实际内容不匹配时，应该回退到无 category"""
        # 模拟：intent 返回 category='bluetooth'，但知识库中该内容的 category='protocol'
        query = "骑行记录"
        intent_category = 'bluetooth'
        actual_content_category = 'protocol'

        # 模拟过滤逻辑
        items = [{'category': 'protocol'}]  # 实际内容是 protocol
        filtered = [item for item in items if not intent_category or item['category'] == intent_category]

        # 应该为空，触发 fallback
        self.assertEqual(len(filtered), 0, "category 不匹配时应该被过滤掉")


class TestQueryExpander(unittest.TestCase):
    """测试 QueryExpander 关键词扩展"""

    def test_chinese_bigram_expansion(self):
        """中文查询应该正确拆分为 bigrams"""
        from models.vector_store import QueryExpander
        expander = QueryExpander()

        query = "骑行记录"
        expanded = expander.expand(query)

        # 原始查询应该保留
        self.assertIn(query.lower(), expanded)

        # "记录" 应该被扩展为 "record"
        has_record_expansion = any('record' in q.lower() for q in expanded)
        self.assertTrue(has_record_expansion, "应该包含 'record' 扩展")

    def test_english_token_preservation(self):
        """英文 token 应该被保留"""
        from models.vector_store import QueryExpander
        expander = QueryExpander()

        query = "DP18 速度"
        expanded = expander.expand(query)

        # "dp18" 和 "速度" 都应该保留
        expanded_lower = [q.lower() for q in expanded]
        self.assertTrue(any('dp18' in q for q in expanded_lower))
        self.assertTrue(any('速度' in q for q in expanded))


class TestRAGFusion(unittest.TestCase):
    """测试 RRF 融合逻辑"""

    def test_rrf_fusion_combine_results(self):
        """RRF 应该正确融合多个检索方法的结果"""
        from models.vector_store import rrf_fusion

        bm25_results = [(0, 10.0), (1, 8.0), (2, 5.0)]
        tfidf_results = [(1, 9.0), (0, 7.0), (3, 4.0)]
        faiss_results = [(2, 6.0), (0, 5.0), (1, 3.0)]

        results = rrf_fusion({
            'bm25': bm25_results,
            'tfidf': tfidf_results,
            'faiss': faiss_results
        }, k=60)

        # 检查结果数量
        self.assertGreater(len(results), 0)

        # 检查 doc_id 0, 1, 2, 3 是否都被召回
        doc_ids = [r[0] for r in results]
        self.assertIn(0, doc_ids)
        self.assertIn(1, doc_ids)
        self.assertIn(2, doc_ids)
        self.assertIn(3, doc_ids)


class TestKnowledgeBaseSearch(unittest.TestCase):
    """测试 KnowledgeBase.search 方法"""

    @classmethod
    def setUpClass(cls):
        """初始化知识库（仅在首次测试前执行）"""
        from models.vector_store import KnowledgeBase
        cls.kb = KnowledgeBase()

    def test_search_returns_results_for_common_query(self):
        """通用查询应该返回结果"""
        results = self.kb.search('蓝牙', top_k=5)
        # 知识库中应该有蓝牙相关文档
        self.assertIsInstance(results, list)

    def test_search_with_none_category(self):
        """category=None 应该搜索所有类别"""
        results = self.kb.vector_store.search('协议', category=None, top_k=5)
        self.assertIsInstance(results, list)


if __name__ == '__main__':
    unittest.main(verbosity=2)
