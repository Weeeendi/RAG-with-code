"""
Recall Test Service
召回测试服务：Ground Truth 管理、Hit Rate @K、MRR 计算
"""
import os
import uuid
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

from config import LABS_DB_PATH


@dataclass
class GroundTruthSet:
    set_id: str
    set_name: str
    description: Optional[str]
    category: Optional[str]
    question_count: int
    avg_difficulty: float
    created_by: Optional[str]
    created_at: str
    updated_at: str


@dataclass
class GroundTruthQuestion:
    qa_id: str
    set_id: str
    question: str
    expected_answer: Optional[str]
    relevant_chunk_ids: List[str]
    difficulty: int
    source: Optional[str]
    created_at: str


@dataclass
class EvaluationResult:
    eval_id: str
    config_id: str
    set_id: str
    question: str
    retrieved_chunk_ids: List[str]
    expected_chunk_ids: List[str]
    hits: int
    hit_rate: float
    mrr: float
    score_distribution: Dict[str, int]
    k_value: int
    evaluated_at: str


class RecallTestService:
    """召回测试服务"""

    def __init__(self, db_path: str = LABS_DB_PATH):
        self.db_path = db_path

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # ========== Ground Truth Sets ==========

    def create_question_set(self, set_name: str, description: str = None,
                           category: str = None, created_by: str = None) -> GroundTruthSet:
        """创建问题集"""
        set_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO ground_truth_sets (set_id, set_name, description, category,
                    created_by, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (set_id, set_name, description, category, created_by, now, now))

            conn.commit()

            return GroundTruthSet(
                set_id=set_id,
                set_name=set_name,
                description=description,
                category=category,
                question_count=0,
                avg_difficulty=1.0,
                created_by=created_by,
                created_at=now,
                updated_at=now
            )

        finally:
            conn.close()

    def get_question_set(self, set_id: str) -> Optional[GroundTruthSet]:
        """获取问题集"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM ground_truth_sets WHERE set_id = ?", (set_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_gt_set(row)

    def list_question_sets(self, category: str = None, limit: int = 50,
                          offset: int = 0) -> List[GroundTruthSet]:
        """列出问题集"""
        conn = self._get_conn()
        cursor = conn.cursor()

        query = "SELECT * FROM ground_truth_sets WHERE 1=1"
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_gt_set(r) for r in rows]

    # ========== Ground Truth Questions ==========

    def add_question(self, set_id: str, question: str,
                    relevant_chunk_ids: List[str] = None,
                    difficulty: int = 3, expected_answer: str = None,
                    source: str = 'manual') -> GroundTruthQuestion:
        """添加问题到问题集"""
        qa_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO ground_truth_questions (
                    qa_id, set_id, question, expected_answer, relevant_chunk_ids,
                    difficulty, source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                qa_id, set_id, question, expected_answer,
                json.dumps(relevant_chunk_ids or []), difficulty, source, now
            ))

            # 更新问题集统计
            cursor.execute('''
                UPDATE ground_truth_sets
                SET question_count = question_count + 1, updated_at = ?
                WHERE set_id = ?
            ''', (now, set_id))

            conn.commit()

            return GroundTruthQuestion(
                qa_id=qa_id,
                set_id=set_id,
                question=question,
                expected_answer=expected_answer,
                relevant_chunk_ids=relevant_chunk_ids or [],
                difficulty=difficulty,
                source=source,
                created_at=now
            )

        finally:
            conn.close()

    def get_questions_by_set(self, set_id: str) -> List[GroundTruthQuestion]:
        """获取问题集的所有问题"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM ground_truth_questions WHERE set_id = ?", (set_id,))
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_gt_question(r) for r in rows]

    # ========== Evaluation ==========

    def evaluate_config(self, config_id: str, set_id: str,
                       k_values: List[int] = None, retrieved_results: List[Dict] = None) -> List[EvaluationResult]:
        """
        对配置进行召回评估

        Args:
            config_id: 实验配置ID
            set_id: 问题集ID
            k_values: K值列表，默认 [1, 3, 5, 10]
            retrieved_results: 检索结果列表，每项包含 question, retrieved_chunk_ids

        Returns:
            评估结果列表
        """
        if k_values is None:
            k_values = [1, 3, 5, 10]

        questions = self.get_questions_by_set(set_id)
        if not questions:
            return []

        results = []
        now = datetime.now().isoformat()

        for question in questions:
            # 模拟检索结果（实际使用时从KnowledgeBase获取）
            if retrieved_results:
                retrieved = next((r for r in retrieved_results if r.get('question') == question.question), None)
                if retrieved:
                    retrieved_chunk_ids = retrieved.get('retrieved_chunk_ids', [])
                else:
                    retrieved_chunk_ids = []
            else:
                # 模拟数据
                retrieved_chunk_ids = question.relevant_chunk_ids[:max(k_values)] if question.relevant_chunk_ids else []

            eval_result = self._compute_metrics(
                config_id=config_id,
                set_id=set_id,
                question=question,
                retrieved_chunk_ids=retrieved_chunk_ids,
                k_values=k_values,
                evaluated_at=now
            )
            results.append(eval_result)

            # 保存评估结果
            self._save_evaluation_result(eval_result)

        return results

    def _compute_metrics(self, config_id: str, set_id: str,
                         question: GroundTruthQuestion,
                         retrieved_chunk_ids: List[str],
                         k_values: List[int],
                         evaluated_at: str) -> EvaluationResult:
        """计算单个问题的评估指标"""
        expected_ids = question.relevant_chunk_ids

        # 计算 Hit Rate @K
        max_k = max(k_values)
        top_k_retrieved = retrieved_chunk_ids[:max_k]

        hits = len(set(top_k_retrieved) & set(expected_ids)) if expected_ids else 0
        hit_rate = hits / len(expected_ids) if expected_ids else 0.0

        # 计算 MRR
        mrr = 0.0
        for i, rid in enumerate(top_k_retrieved):
            if rid in expected_ids:
                mrr = 1.0 / (i + 1)
                break

        # 计算分数分布（模拟）
        score_distribution = {
            "0.0-0.2": 0,
            "0.2-0.4": 0,
            "0.4-0.6": 0,
            "0.6-0.8": 0,
            "0.8-1.0": 0
        }
        for _ in retrieved_chunk_ids:
            # 模拟分数分布
            import random
            score = random.random()
            if score < 0.2:
                score_distribution["0.0-0.2"] += 1
            elif score < 0.4:
                score_distribution["0.2-0.4"] += 1
            elif score < 0.6:
                score_distribution["0.4-0.6"] += 1
            elif score < 0.8:
                score_distribution["0.6-0.8"] += 1
            else:
                score_distribution["0.8-1.0"] += 1

        return EvaluationResult(
            eval_id=str(uuid.uuid4()),
            config_id=config_id,
            set_id=set_id,
            question=question.question,
            retrieved_chunk_ids=retrieved_chunk_ids,
            expected_chunk_ids=expected_ids,
            hits=hits,
            hit_rate=hit_rate,
            mrr=mrr,
            score_distribution=score_distribution,
            k_value=max_k,
            evaluated_at=evaluated_at
        )

    def _save_evaluation_result(self, result: EvaluationResult):
        """保存评估结果"""
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO recall_evaluations (
                    eval_id, config_id, set_id, question, retrieved_chunk_ids,
                    expected_chunk_ids, hits, hit_rate, mrr, score_distribution,
                    k_value, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                result.eval_id, result.config_id, result.set_id, result.question,
                json.dumps(result.retrieved_chunk_ids), json.dumps(result.expected_chunk_ids),
                result.hits, result.hit_rate, result.mrr, json.dumps(result.score_distribution),
                result.k_value, result.evaluated_at
            ))

            conn.commit()

        finally:
            conn.close()

    def get_evaluation_results(self, config_id: str = None, set_id: str = None) -> List[EvaluationResult]:
        """获取评估结果"""
        conn = self._get_conn()
        cursor = conn.cursor()

        query = "SELECT * FROM recall_evaluations WHERE 1=1"
        params = []

        if config_id:
            query += " AND config_id = ?"
            params.append(config_id)
        if set_id:
            query += " AND set_id = ?"
            params.append(set_id)

        query += " ORDER BY evaluated_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_eval_result(r) for r in rows]

    def get_aggregate_metrics(self, config_id: str) -> Dict[str, Any]:
        """计算聚合指标"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                AVG(hit_rate) as avg_hit_rate,
                AVG(mrr) as avg_mrr,
                COUNT(*) as eval_count,
                SUM(hits) as total_hits
            FROM recall_evaluations
            WHERE config_id = ?
        ''', (config_id,))

        row = cursor.fetchone()
        conn.close()

        if not row or row['eval_count'] == 0:
            return {}

        return {
            "avg_hit_rate": row['avg_hit_rate'] or 0,
            "avg_mrr": row['avg_mrr'] or 0,
            "eval_count": row['eval_count'],
            "total_hits": row['total_hits'] or 0
        }

    # ========== Helper Methods ==========

    def _row_to_gt_set(self, row) -> GroundTruthSet:
        if hasattr(row, 'keys'):
            row = dict(row)

        return GroundTruthSet(
            set_id=row['set_id'],
            set_name=row['set_name'],
            description=row.get('description'),
            category=row.get('category'),
            question_count=row.get('question_count', 0),
            avg_difficulty=row.get('avg_difficulty', 1.0),
            created_by=row.get('created_by'),
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )

    def _row_to_gt_question(self, row) -> GroundTruthQuestion:
        if hasattr(row, 'keys'):
            row = dict(row)

        chunk_ids_str = row.get('relevant_chunk_ids', '[]')
        chunk_ids = json.loads(chunk_ids_str) if chunk_ids_str else []

        return GroundTruthQuestion(
            qa_id=row['qa_id'],
            set_id=row['set_id'],
            question=row['question'],
            expected_answer=row.get('expected_answer'),
            relevant_chunk_ids=chunk_ids,
            difficulty=row.get('difficulty', 3),
            source=row.get('source'),
            created_at=row['created_at']
        )

    def _row_to_eval_result(self, row) -> EvaluationResult:
        if hasattr(row, 'keys'):
            row = dict(row)

        retrieved_str = row.get('retrieved_chunk_ids', '[]')
        expected_str = row.get('expected_chunk_ids', '[]')
        dist_str = row.get('score_distribution', '{}')

        return EvaluationResult(
            eval_id=row['eval_id'],
            config_id=row['config_id'],
            set_id=row['set_id'],
            question=row['question'],
            retrieved_chunk_ids=json.loads(retrieved_str) if retrieved_str else [],
            expected_chunk_ids=json.loads(expected_str) if expected_str else [],
            hits=row.get('hits', 0),
            hit_rate=row.get('hit_rate', 0),
            mrr=row.get('mrr', 0),
            score_distribution=json.loads(dist_str) if dist_str else {},
            k_value=row.get('k_value', 10),
            evaluated_at=row['evaluated_at']
        )
