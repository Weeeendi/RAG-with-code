# 代码知识蒸馏系统

## 1. 概述

代码知识蒸馏（Code Distillation）是将源码从"执行指令集"转化为"逻辑描述集"的过程，使Agent能够理解代码的深层逻辑，同时保护知识产权。

## 2. 系统架构

```
源码 (.c/.h)
    ↓
┌─────────────────────────────────────────┐
│  结构化抽取 (Code Analysis)              │
│  ├── CallGraphExtractor - 调用图          │
│  ├── RelationshipMapper - 关系映射        │
│  └── LogicSkeletonExtractor - 逻辑骨架   │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  代码蒸馏 (Code Distiller)               │
│  └── LLM生成业务逻辑描述                 │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  知识图谱 (Knowledge Graph Store)        │
│  ├── code_nodes - 蒸馏后的逻辑节点       │
│  └── code_edges - 调用/依赖关系边        │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  Graph RAG检索 (GraphRAGEngine)         │
│  ├── 关键词匹配 → 节点扩展 → 边遍历     │
│  └── 业务逻辑链构建                      │
└─────────────────────────────────────────┘
```

## 3. 核心组件

### 3.1 CallGraphExtractor

提取函数调用关系，构建模块级调用图。

```python
from models.code_analysis import CallGraphExtractor

extractor = CallGraphExtractor(source_dir)
call_graph = extractor.extract_from_directory()

# 获取协议相关函数
protocol_funcs = extractor.get_protocol_related_functions()
```

**输出**: 868个函数节点, 126个模块

### 3.2 RelationshipMapper

映射struct/enum与函数关系，建立DP与处理函数的绑定。

```python
from models.code_analysis import RelationshipMapper

mapper = RelationshipMapper(source_dir)
rel_graph = mapper.extract_from_directory()

# 获取struct对应的函数
funcs = mapper.get_functions_for_struct("vl_dp_obj")
```

### 3.3 LogicSkeletonExtractor

提取状态机和协议处理流程。

```python
from models.code_analysis import LogicSkeletonExtractor

extractor = LogicSkeletonExtractor(source_dir)
logic_data = extractor.extract_from_directory()

# 输出: state_machines, protocol_flows
```

### 3.4 CodeDistiller

LLM生成业务逻辑描述。

```python
from models.code_distiller import CodeDistiller

distiller = CodeDistiller()
result = distiller.distill_function(code_snippet, "handle_ble_event")
```

**输入示例**:
```c
if (retry_count > 3) {
    send_error(0x31);
}
```

**输出示例**:
```json
{
    "functionality": "重试机制",
    "business_logic": "当重试超过3次时，系统触发0x31错误状态码进行状态同步",
    "key_conditions": ["重试次数 > 3"],
    "outputs": ["发送0x31错误码"],
    "business_terms": ["状态同步", "错误处理"]
}
```

### 3.5 KnowledgeGraphStore

SQLite图数据库存储。

```python
from models.code_distiller import KnowledgeGraphStore

store = KnowledgeGraphStore()

# 添加节点
store.add_node(distilled_knowledge, module_name="BLE", file_path="...", line_number=123)

# 添加边
store.add_edge("func_handle_event", "func_send_response", edge_type="calls")

# 检索相关节点
related = store.get_related_nodes("func_handle_event", depth=2)
```

### 3.6 GraphRAGEngine

基于图的检索引擎。

```python
from models.graph_rag_engine import GraphRAGEngine

graph_rag = GraphRAGEngine(source_dir)
graph_rag.index_codebase()

# 检索
results = graph_rag.retrieve_with_graph("骑行记录如何上报", top_k=5)

# 获取DP相关的逻辑链
chain = graph_rag.get_logic_chain_for_dp("DP18")
```

## 4. 黑盒化策略

### 4.1 语义替代 (Semantic Replacement)

利用CODE_TO_BUSINESS_MAP将代码术语转为业务描述：

```python
# 输入: VL_BLE_EVT_PAIR
# 输出: 配对请求
```

### 4.2 引用隔离 (Reference-only Retrieval)

Agent内部可访问节点ID和逻辑描述，但输出受限：

```
禁止: 变量名、函数签名、具体算法
允许: 业务逻辑描述、功能概述
```

### 4.3 结构元素提取

保留代码结构信息，但不暴露具体实现：

```python
from models.graph_rag_engine import BlackBoxProcessor

elements = BlackBoxProcessor.extract_structural_elements(code)
# 输出: has_loop=True, has_condition=True, complexity_estimate=3
```

## 5. 数据表结构

### code_nodes

| 字段 | 类型 | 说明 |
|------|------|------|
| node_id | TEXT | 主键 |
| node_type | TEXT | function/state_machine/struct |
| name | TEXT | 名称 |
| distilled_logic | TEXT | LLM生成的逻辑描述(JSON) |
| business_description | TEXT | 业务描述 |
| keywords | TEXT | 关键词(逗号分隔) |
| module_name | TEXT | 所属模块 |
| file_path | TEXT | 源文件路径 |
| line_number | INTEGER | 行号 |
| metadata | TEXT | 额外元数据(JSON) |

### code_edges

| 字段 | 类型 | 说明 |
|------|------|------|
| edge_id | INTEGER | 主键 |
| from_node | TEXT | 起始节点 |
| to_node | TEXT | 目标节点 |
| edge_type | TEXT | calls/depends_on/implements |
| description | TEXT | 边描述 |

## 6. 使用流程

### 6.1 索引代码库

```python
from models.graph_rag_engine import GraphRAGEngine

graph_rag = GraphRAGEngine()
stats = graph_rag.index_codebase(source_dir)

print(f"Indexed: {stats['functions_indexed']} functions, {stats['state_machines_indexed']} state machines")
```

### 6.2 检索并构建回答

```python
# 检索
results = graph_rag.retrieve_with_graph("骑行记录生成逻辑")

# 构建上下文
context = graph_rag.build_answer_context(query, results)
```

### 6.3 Agent集成

在ReActRAGEngine中，search_code工具调用GraphRAG：

```python
# 当发现DP ID后，强制检索代码实现
results = graph_rag.retrieve_with_graph(f"DP{dp_id}")
```

## 7. 注意事项

- LLM蒸馏需要MiniMax API Key
- 图索引是增量更新的，已存在的节点不会重复处理
- 原始代码不存储在graph_db中，仅存储蒸馏后的逻辑
- 输出时自动应用BlackBoxProcessor过滤