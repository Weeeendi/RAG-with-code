# 搜索性能优化计划

## 背景问题

当前知识库搜索存在以下性能问题：

| 问题 | 位置 | 影响 |
|------|------|------|
| BM25/TFIDF 每次搜索都 fit 所有文档 | `vector_store.py:1002-1006` | 搜索耗时 >30s |
| `find_relevant_files` 遍历所有文件 | `vector_store.py:876` | 接近 10s 超时 |
| `get_items_by_file` 重复调用 | `vector_store.py:883,901` | 额外 DB 查询 |
| 分类失衡：c_code 40081条 vs protocol 321条 | 数据库 | 协议文档易被淹没 |

数据库规模：31.34 MB，40,415 条记录

---

## Phase 1：基础性能优化

**目标**：消除明显瓶颈，快速见效

### 1.1 BM25/TFIDF 结果缓存

**问题**：`search()` 方法每次都创建新的 BM25 和 TFIDF 对象，并 fit 所有文档

**优化方案**：
```python
# 基于 (file_path + content_hash) 缓存已计算的 BM25/TFIDF 索引
_cache_key = f"{file_path}_{hash(content)}"
if _cache_key in self._bm25_cache:
    return self._bm25_cache[_cache_key]
```

**预期效果**：搜索耗时从 >30s 降到 <5s

### 1.2 `find_relevant_files` 超时调整

**问题**：超时 10s 不足，文件遍历容易超时

**优化方案**：调整 TIMEOUT_SEC = 30

### 1.3 查询日志埋点

**优化方案**：添加 QPS 和延迟监控

```python
# 在 search() 方法中添加
import time
t0 = time.time()
# ... 搜索逻辑 ...
latency = time.time() - t0
logger.info(f"search latency: {latency:.3f}s, query: {query}")
```

---

## Phase 2：检索架构升级

**目标**：引入向量数据库，从 O(n) 降到 O(log n)

### 2.1 引入 FAISS 向量数据库

**方案**：使用 FAISS 作为向量检索后端

```python
import faiss
import numpy as np

# 构建向量索引
dimension = 384  # embedding 维度
index = faiss.IndexFlatIP(dimension)  # 内积索引

# 添加向量
index.add(vectors)

# ANN 搜索
D, I = index.search(query_vector, k=10)
```

### 2.2 Embedding Pipeline

**方案**：使用 sentence-transformers 生成文档向量

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
embeddings = model.encode(documents)
```

### 2.3 HNSW 索引

**方案**：替换 FlatIP 为 HNSW，提升大数据集性能

```python
index = faiss.IndexHNSWFlat(dimension, 32)  # M=32
index.hnsw.efSearch = 64
index.hnsw.efConstruction = 40
```

**⚠️ 问题**：Windows环境下faiss-cpu 1.8.0的HNSW存在segfault，暂使用FlatIP替代

**状态**：待解决（TODO）

---

## Phase 3：索引体系建设

**目标**：降低搜索范围，提高命中率

### 3.1 知识分类与分片

**问题**：c_code 占 99%，协议文档易被淹没

**优化方案**：
- 按 category 分开索引：c_code / protocol / log
- 协议文档优先：BLE 协议问题只搜索 protocol 分片

**状态**：✅ 已实现（利用数据库idx_category索引）

### 3.2 Query 意图分类器

**问题**：用户问 BLE 协议，却被路由到 C 代码

**优化方案**：根据问题类型路由到对应知识库

**状态**：✅ 已实现

```python
# models/vector_store.py:1313-1366
class QueryIntentClassifier:
    CATEGORY_PATTERNS = {
        'protocol': ['BLE', '蓝牙', '配对', '绑定', 'HID', 'OTA', 'RS485', 'CAN', ...],
        'log': ['log', '日志', 'error', '错误', 'fault', '故障', ...],
        'c_code': ['struct', 'function', 'enum', 'macro', 'typedef', ...]
    }
```

### 3.3 多知识库分片

**优化方案**：将大文件分片存储

**状态**：✅ 已实现（通过parent_id支持文档层级）

```python
# 大文件通过parent_id关联子条目
parent_id支持文档层级结构
```

---

**Phase 3 效果**：
- BLE协议查询：30s → 2.6s（分类路由生效）
- 非分类查询：仍需遍历全量文件

---

## Phase 4：效果优化

**目标**：提升回答质量

### 4.1 多路召回

**方案**：关键词 + 向量 + 分类权重融合

**状态**：✅ 已实现

```python
# models/vector_store.py:1146-1150
results_bm25 = bm25_search(query, top_k=50)
results_vector = vector_search(query, top_k=50)  # FAISS
results_reranked = rrf_fusion({'bm25': ..., 'tfidf': ..., 'faiss': ...}, k=60)
```

### 4.2 Cross-encoder Rerank

**方案**：对 Top 结果用 Cross-encoder 重排序

**状态**：✅ 已实现

```python
# models/vector_store.py:1185-1202
def _rerank_with_crossencoder(self, query, candidates):
    model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
    doc_pairs = [(query, r['content_preview']) for r in candidates]
    scores = model.predict(doc_pairs)
    # 按cross_score重排序
```

### 4.3 Query Rewrite

**方案**：用 LLM 改写查询，提升召回率

**状态**：✅ QueryExpander已实现（见Phase 1）

```python
# models/vector_store.py:107 - QueryExpander类
# 支持同义词扩展、技术术语扩展、中英翻译等
# 注：为性能考虑，当前限制为1个查询
```

---

## 执行计划

| 阶段 | 任务 | 优先级 | 状态 | 实际效果 |
|------|------|--------|------|----------|
| Phase 1 | BM25缓存 | P0 | ✅ | >30s → <5s (协议查询) |
| Phase 1 | 超时调整 | P0 | ✅ | 避免超时 |
| Phase 1 | 查询日志 | P1 | ✅ | [SEARCH] 日志 |
| Phase 2 | FAISS集成 | P1 | ✅ | 向量检索(FlatIP) |
| Phase 2 | HNSW索引 | P1 | ⚠️ | Windows segfault，待解决 |
| Phase 3 | 分类索引 | P1 | ✅ | 协议查询加速 |
| Phase 3 | Query路由 | P2 | ✅ | 30s→2.6s |
| Phase 4 | 多路召回 | P2 | ✅ | BM25+TFIDF+FAISS RRF |
| Phase 4 | Rerank | P3 | ✅ | Cross-encoder ms-marco-MiniLM-L-6-v2 |

---

## 待解决事项

1. ⚠️ **HNSW segfault**：Windows环境下faiss-cpu HNSW不稳定，需Linux环境或conda安装
2. ❌ **非分类查询**：通用查询仍需遍历全量1252文件，约30s

---

## Phase 5：代码知识蒸馏（2024年新增）

**目标**：利用源码深度逻辑，但不暴露源码内容

### 5.1 结构化抽取

| 组件 | 文件 | 功能 |
|------|------|------|
| CallGraphExtractor | `code_analysis/call_graph.py` | 提取函数调用关系(868节点) |
| RelationshipMapper | `code_analysis/relationship_mapper.py` | struct/enum与函数关系映射 |
| LogicSkeletonExtractor | `code_analysis/logic_skeleton.py` | 状态机提取 |

### 5.2 代码蒸馏管道

```python
# 输入: 源码片段
# 输出: 业务逻辑描述
if (retry_count > 3) { send_error(0x31); }
    ↓
"当重试超过3次时，系统触发0x31错误状态码进行状态同步"
```

### 5.3 Graph RAG

| 组件 | 功能 |
|------|------|
| KnowledgeGraphStore | SQLite图存储(code_nodes + code_edges) |
| GraphRAGEngine | 基于图的检索，边遍历扩展 |

### 5.4 黑盒化策略

- **语义替代**: CODE_TO_BUSINESS_MAP将代码术语转业务描述
- **引用隔离**: 仅存储蒸馏后逻辑，原码不暴露
- **结构元素**: 仅保留代码结构(循环/分支)，不暴露具体实现

### 5.5 分级检索增强

| 级别 | 内容 | 触发条件 |
|------|------|----------|
| 一级 | 协议术语精确匹配 | 初始检索 |
| 二级 | 语义扩展(trip_data, history_record) | 一级无结果 |
| 三级 | 代码深挖(search_code) | 二级不足 |

### 5.6 回答模板

```
[触发机制]
<业务触发条件>

[数据结构]
<数据格式定义>

[代码参考]
<关键函数或位置>

[技术推论]
<基于代码的推断>
```

---

## Phase 5 执行状态

| 任务 | 状态 | 说明 |
|------|------|------|
| 调用图提取 | ✅ | 868节点, 126模块 |
| 关系映射 | ✅ | struct/enum/DP绑定 |
| 逻辑骨架 | ✅ | 状态机/协议流程 |
| 代码蒸馏 | ✅ | LLM生成业务描述 |
| 图存储 | ✅ | SQLite图数据库 |
| Graph检索 | ✅ | 边遍历扩展 |
| 黑盒处理 | ✅ | BlackBoxProcessor |
| 分级检索 | ✅ | 自动回退机制 |
| 结构化回答 | ✅ | 四要素模板 |