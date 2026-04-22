import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
import jieba
jieba.initialize()
jiebaLogger = logging.getLogger('jieba')
jiebaLogger.setLevel(logging.WARNING)
jiebaLogger.propagate = False

from typing import Dict, List, Any, Optional
from .vector_store import KnowledgeBase
from .intent_classifier import IntentClassifier


class RAGEngine:
    INTENT_CATEGORY_PRIORITY = {
        'can': ['protocol', 'c_code'],
        'bluetooth': ['protocol', 'c_code'],
        'mqtt': ['c_code'],
        'dp': ['c_code'],
        'business': ['c_code', 'protocol'],
        'log': ['log'],
    }

    def __init__(self, knowledge_base: KnowledgeBase):
        self.kb = knowledge_base
        self.intent_classifier = IntentClassifier()

    def retrieve(self, query: str, category: str = None, top_k: int = 5) -> List[Dict[str, Any]]:
        if category is None:
            intent = self.intent_classifier.classify(query)
            category = intent.category

        categories_to_try = self.INTENT_CATEGORY_PRIORITY.get(category, ['c_code', 'protocol'])

        search_results = []
        all_results = {}

        for cat in categories_to_try:
            items = self.kb.search(query, category=cat, top_k=top_k)
            for item in items:
                doc_id = item.id
                search_results.append({
                    'id': item.id,
                    'type': item.type,
                    'category': item.category,
                    'title': item.title,
                    'content': item.content,
                    'source_file': item.source_file,
                    'line_number': item.line_number,
                    'score': 1.0
                })
            if items:
                break

        if not search_results:
            for cat in ['c_code', 'protocol', 'log']:
                if cat not in categories_to_try:
                    items = self.kb.search(query, category=cat, top_k=5)
                    for item in items:
                        search_results.append({
                            'id': item.id,
                            'type': item.type,
                            'category': item.category,
                            'title': item.title,
                            'content': item.content,
                            'source_file': item.source_file,
                            'line_number': item.line_number,
                            'score': 1.0
                        })
                    if search_results:
                        break

        image_keywords = ['图片', 'image', '截图', '图示', '示意图', '流程图', '框图']
        if any(kw in query for kw in image_keywords):
            image_items = self.kb.search(query, category='protocol', top_k=3)
            for item in image_items:
                if item.type == 'image':
                    search_results.append({
                        'id': item.id,
                        'type': item.type,
                        'category': item.category,
                        'title': item.title,
                        'content': item.content,
                        'source_file': item.source_file,
                        'line_number': item.line_number,
                        'score': 1.5
                    })

        return search_results[:top_k]

    def build_context(self, retrieved_docs: List[Dict[str, Any]], max_chars: int = 4000) -> str:
        if not retrieved_docs:
            return "未找到相关知识库内容。"

        context_parts = []
        current_length = 0

        for doc in retrieved_docs:
            doc_type = doc.get('type', 'unknown')
            doc_category = doc.get('category', '')
            title = doc.get('title', 'Untitled')
            content = doc.get('content', '')[:600]

            if doc_category == 'protocol':
                doc_text = f"""
【协议文档】{title}
内容:
{content}
"""
            elif doc_category == 'c_code':
                doc_text = f"""
【代码实现】{title}
实现说明:
{content}
"""
            elif doc_category == 'log':
                doc_text = f"""
【日志】{title}
内容:
{content[:300]}
"""
            elif doc_type == 'image':
                doc_text = f"""
【图片】{title}
{content}
"""
            else:
                doc_text = f"""
【{doc_type}】{title}
内容:
{content[:400]}
"""

            if current_length + len(doc_text) > max_chars:
                break
            context_parts.append(doc_text)
            current_length += len(doc_text)

        return "\n---\n".join(context_parts)


class AnswerGenerator:
    def __init__(self, api_key: str, base_url: str = "https://api.minimax.chat/v1"):
        self.api_key = api_key
        self.base_url = base_url

    def generate(
        self,
        question: str,
        context: str,
        category: str,
        history: List[Dict[str, str]] = None
    ) -> str:
        system_prompt = self._get_system_prompt(category)
        user_prompt = self._build_user_prompt(question, context, category)

        try:
            import requests
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "MiniMax-M2.7",
                "max_tokens": 800,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ]
            }
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30
            )
            if response.status_code == 200:
                result = response.json()
                if result.get("choices") and result["choices"][0].get("message", {}).get("content"):
                    return result["choices"][0]["message"]["content"]
            return f"API错误: {response.status_code} - {response.text}"
        except Exception as e:
            return f"生成回答时出错: {str(e)}"

    def _get_system_prompt(self, category: str) -> str:
        base = """你是一个专业的物联网技术支持助手，基于提供的知识库内容回答用户问题。

【重要规则】
1. 协议文档内容可以直接引用和暴露给用户
2. 源码/代码实现不能直接暴露，只能用于理解业务行为
3. 回答时用自然语言描述业务行为，不要出现函数名、变量名等源码细节
4. 如果只有源码信息，请基于源码理解后用业务语言描述，不要复制函数名

回答要求：
1. 准确、简洁，专业
2. 如果知识库中没有相关内容，明确告知用户
3. 涉及协议时，说明帧格式和交互流程
4. 描述业务行为时，用用户能理解的语言

回答格式：
- 核心答案放前面
- 协议相关用清晰的格式说明
- 业务行为用自然语言描述
"""
        category_hints = {
            "bluetooth": "问题涉及蓝牙协议，请重点关注BLE帧格式、GATT服务和特征值、广播交互流程",
            "can": "问题涉及CAN总线协议，请关注帧ID、数据长度(DLC)、字节序和交互时序",
            "mqtt": "问题涉及MQTT协议，请关注Topic订阅/发布机制、Payload格式、QoS级别",
            "dp": "问题涉及物模型/数据点(DP)，请说明DP格式、字段含义和业务场景",
            "business": "问题涉及业务逻辑，请结合设备端代码和云端交互流程说明",
            "log": "问题涉及日志分析，请指出可能的错误原因和排查方向"
        }
        base += "\n\n图片引用规则：当检索结果包含【图片】时，在回答中应引用图片路径，并说明图片展示的内容。格式：![说明](图片路径)"
        if category in category_hints:
            base += f"\n\n补充说明：{category_hints[category]}"
        return base

    def _build_user_prompt(self, question: str, context: str, category: str) -> str:
        return f"""## 用户问题
{question}

## 知识库检索结果
{context}

## 请基于以上内容回答用户问题。
如果检索结果中没有直接相关的内容，请根据你的物联网知识给出一般性回答，并明确说明这一点。
"""


class FAQAgent:
    def __init__(self, knowledge_base: KnowledgeBase, answer_generator: AnswerGenerator):
        self.rag = RAGEngine(knowledge_base)
        self.generator = answer_generator

    def ask(
        self,
        question: str,
        category: str = None,
        history: List[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        logger = logging.getLogger(__name__)

        import time
        t0 = time.time()
        intent = self.rag.intent_classifier.classify(question)
        t1 = time.time()
        logger.info(f"[计时] 意图分类: {t1-t0:.2f}s")

        target_category = category or intent.category

        t2 = time.time()
        retrieved = self.rag.retrieve(question, target_category, top_k=5)
        t3 = time.time()
        logger.info(f"[计时] RAG检索: {t3-t2:.2f}s")

        context = self.rag.build_context(retrieved)

        t4 = time.time()
        answer = self.generator.generate(question, context, target_category, history)
        t5 = time.time()
        logger.info(f"[计时] API生成: {t5-t4:.2f}s")
        logger.info(f"[计时] 总耗时: {t5-t0:.2f}s")

        return {
            "question": question,
            "answer": answer,
            "category": target_category,
            "confidence": intent.confidence,
            "retrieved_count": len(retrieved),
            "intent": {
                "category": intent.category,
                "confidence": intent.confidence,
                "keywords_matched": intent.keywords_matched
            }
        }

    def add_to_knowledge_base(
        self,
        content: str,
        content_type: str,
        title: str,
        category: str = "business",
        source: str = "manual"
    ):
        import uuid
        doc_id = str(uuid.uuid4())
        doc = {
            "id": doc_id,
            "type": content_type,
            "title": title,
            "content": content,
            "source": source,
            "scene": ""
        }

        if content_type in ["c_code", "struct", "enum", "function", "macro", "state_machine"]:
            self.rag.kb.add_c_code([doc])
        elif content_type in ["protocol_doc", "frame_format"]:
            self.rag.kb.add_protocol_docs([doc])
        elif content_type == "log":
            self.rag.kb.add_logs([doc])
        else:
            self.rag.kb.add_protocol_docs([doc])

    def record_feedback(self, question: str, answer: str, is_resolved: bool):
        self.rag.kb.add_feedback(question, answer, is_resolved)

    def get_unresolved_feedback(self) -> List[Dict[str, Any]]:
        return self.rag.kb.get_unresolved_questions()

    def fix_knowledge_from_feedback(self, feedback_id: int, corrected_content: str) -> bool:
        feedback_list = self.get_unresolved_feedback()
        target_feedback = None
        for fb in feedback_list:
            if fb['id'] == feedback_id:
                target_feedback = fb
                break

        if not target_feedback:
            return False

        related_items = self.rag.kb.find_related_items(target_feedback['question'], limit=3)

        if related_items:
            self.rag.kb.update_knowledge_item(
                related_items[0].id,
                content=corrected_content
            )
            self.rag.kb.metadata_db.resolve_feedback(feedback_id, corrected_content)
            return True

        return False

    def delete_wrong_knowledge(self, feedback_id: int) -> bool:
        feedback_list = self.get_unresolved_feedback()
        target_feedback = None
        for fb in feedback_list:
            if fb['id'] == feedback_id:
                target_feedback = fb
                break

        if not target_feedback:
            return False

        related_items = self.rag.kb.find_related_items(target_feedback['question'], limit=1)

        if related_items:
            self.rag.kb.delete_knowledge_item(related_items[0].id)
            self.rag.kb.metadata_db.resolve_feedback(feedback_id, "[DELETED]")
            return True

        return False