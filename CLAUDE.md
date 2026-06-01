# Project

物联网技术支持Agent - 基于RAG技术的智能问答系统

## 功能

解析并索引C代码、协议文档和日志，利用MiniMax API通过RAG技术回答物联网设备相关的技术问题。

## 核心特性

- **分级检索**: 协议优先 → 语义扩展 → 代码深挖 三级自动回退
- **Graph RAG**: 代码知识图谱，支持调用链追溯和跨域联动
- **代码蒸馏**: 将源码转化为业务逻辑描述，保护知识产权
- **结构化回答**: 触发机制、涉及协议内容、操作说明、引用来源 4要素模板

## 目录结构

- `main.py` - 主入口，交互式问答模式
- `config.py` - 配置文件（API密钥、路径等）
- `models/` - 核心模块
  - `vector_store.py` - 向量知识库 (BM25+TF-IDF+FAISS RRF融合)
  - `c_parser.py` - C代码解析器
  - `protocol_parser.py` - 协议文档解析器 (支持PDF表格提取)
  - `log_parser.py` - 日志解析器
  - `rag_engine.py` - RAG引擎和问答代理
  - `intent_classifier.py` - 意图分类器
  - `tool_executor.py` - 统一工具调度器 (支持PDF/MD/Excel表格)
  - `enhanced_rag_engine.py` - 增强RAG引擎 (ReAct+分级检索+语义扩展)
  - `minimax_embedding.py` - MiniMax嵌入接口 (embo-01)
  - `code_analysis/` - 代码结构分析
    - `call_graph.py` - 调用图提取
    - `relationship_mapper.py` - 关系映射
    - `logic_skeleton.py` - 逻辑骨架提取
  - `code_distiller.py` - 代码蒸馏管道 (LLM生成业务描述)
  - `graph_rag_engine.py` - Graph RAG检索引擎
  - `utils/` - 工具类
    - `text_cleaner.py` - 文本清洗 (竖排字符规范化)
    - `chunker.py` - 智能分块 (SmartChunker)
- `labs/` - 数据-检索闭环实验室 (Data-to-Retrieval Loop)
  - `data_retrieval_loop/` - 实验室核心模块
    - `api/` - Flask API路由
    - `models/` - 数据模型
    - `services/` - 业务逻辑服务
    - `tasks/` - 后台异步任务
    - `utils/` - 工具函数
- `knowledge_base/` - 知识库源码
  - `raw/` - 原始文件（C代码、协议文档、日志）
  - `vectorized/` - 向量化后的数据
  - `parsed/` - 解析后的文档缓存
- `data/` - SQLite数据库存储

## 启动

```bash
python main.py
```

## 依赖

- MiniMax API Key
- sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2)
- SQLite, scikit-learn, faiss-cpu
- pdfplumber, openpyxl, python-docx

## 检索架构

### 分级检索策略

1. **一级检索（协议优先）**: 精确协议术语（DP ID、命令码）
2. **二级检索（语义扩展）**: 同义词近义词（trip_data, history_record）
3. **三级检索（代码深挖）**: 强制检索代码实现

### 向量检索融合

```
BM25 + TF-IDF + FAISS (FlatIP) → RRF融合 → Cross-Encoder重排
```

### Graph RAG

- **节点**: 函数、结构体、状态机、协议处理
- **边**: calls（调用）、depends_on（依赖）、implements（实现）
- **检索**: 关键词匹配 → 节点扩展 → 边遍历

## 工具管理

所有文档解析工具通过 `models/tool_executor.py` 的 `ToolExecutor` 统一管理。

详见 [工具管理规范](docs/tool_management.md)。

### 新增工具流程

1. 在 `models/tool_executor.py` 中添加解析方法
2. 在 `_register_default_tools()` 中注册
3. 在 `models/__init__.py` 中导出

## 代码知识蒸馏

代码通过以下流程转化为业务逻辑描述：

1. **结构化抽取**: CallGraphExtractor提取调用图
2. **关系映射**: RelationshipMapper建立DP与函数绑定
3. **逻辑骨架**: LogicSkeletonExtractor提取状态机
4. **LLM蒸馏**: CodeDistiller生成业务描述
5. **图存储**: KnowledgeGraphStore存储节点和边

详见 [代码蒸馏系统](docs/code_distillation.md)。

## 回答模板

最终回答必须包含四要素：

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

## 数据-检索闭环实验室 (Data-to-Retrieval Loop Lab)

实验室模块用于优化文档分块和检索效果，提供独立的测试环境。

### 核心功能

1. **资产管理中心** (`/api/labs/assets`)
   - 文件上传/删除/状态监控
   - MD5/SHA256 校验防止重复处理
   - 状态机: `uploaded → parsing → parsed → indexing → indexed`

2. **实验配置区** (`/api/labs/experiments`)
   - 分块参数: Chunk Size (500/800/1000), Overlap (10%/15%)
   - 影子索引: 创建 `Test_v1` 临时索引，不覆盖原索引
   - 多方案对比

3. **召回测试场** (`/api/labs/recall`)
   - Ground Truth 问题集管理
   - Hit Rate @K, MRR 指标
   - 分数分布可视化

4. **溯源可视化器** (`/api/labs/provenance`)
   - 分块 → 原始 PDF 位置映射
   - 坐标高亮定位

### API 端点

| 方法 | 端点 | 描述 |
|------|------|------|
| POST | `/api/labs/assets/upload` | 上传文件 |
| GET | `/api/labs/assets` | 资产列表 |
| DELETE | `/api/labs/assets/<id>` | 删除资产 |
| POST | `/api/labs/experiments` | 创建实验配置 |
| POST | `/api/labs/experiments/<id>/activate` | 激活配置(创建影子索引) |
| POST | `/api/labs/recall/sets/<id>/evaluate` | 执行召回评估 |
| GET | `/api/labs/provenance/chunk/<id>` | 获取分块溯源 |

详见 [数据-检索闭环设计](docs/data_retrieval_loop.md)。

### 数据库表

- `asset_registry` - 文件资产管理
- `experiment_configs` - 实验配置
- `ground_truth_sets` / `ground_truth_questions` - 测试问题集
- `recall_evaluations` - 评估结果
- `asset_chunk_mapping` - 分块溯源映射
- `processing_tasks` - 异步任务追踪

## 工程准则

### 1. 功能必须真实现，不允许示例数据
**原则**：每个功能必须按业务逻辑真正实现，禁止使用示例数据或stub代码。

**具体要求**：
- 所有按钮、API调用必须连接到真实后端
- 进度条必须显示真实处理状态
- 统计数据必须来自实际数据库查询
- 文件上传必须真正解析并入库
- 删除操作必须真实删除数据

**例外**：调试用的模拟数据仅限于开发测试阶段，但必须标注并尽快替换。

### 2. 前端交互必须完整
- 每个按钮有对应的实际功能
- 加载状态显示真实进度
- 错误提示必须明确原因
- 空状态必须引导用户操作

### 3. API设计原则
- RESTful风格，路径清晰
- 响应包含success/data/error结构
- 状态码正确（200/400/404/500）
- 支持分页和过滤

### 4. 数据一致性
- 前端展示的数据必须与后端一致
- 列表操作后必须刷新
- 删除/创建后状态同步更新