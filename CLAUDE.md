# Project

物联网技术支持Agent - 基于RAG技术的智能问答系统

## 功能

解析并索引C代码、协议文档和日志，通过RAG技术回答物联网设备相关的技术问题。

## 核心特性

- **分级检索**: 协议优先 → 语义扩展 → 代码深挖 三级自动回退
- **可插拔模型**: LLM/Embedding/Rerank 支持灵活配置切换
- **结构化回答**: 触发机制、数据结构、技术推论 3要素模板

## 目录结构

- `main.py` - 主入口，交互式问答模式
- `config.py` - 配置文件（模型选择、API密钥、路径等）
- `models/` - 核心模块
  - `provider.py` - 模型provider工厂（LLM/Embedding/Rerank）
  - `llm_provider.py` - LLM接口抽象（MiniMax/SiliconFlow/OpenAI兼容）
  - `rerank_provider.py` - Rerank接口抽象（CrossEncoder/SiliconFlow/NoOp）
  - `silicon_embedding.py` - 向量化接口（SiliconFlow/TF-IDF）
  - `vector_store.py` - 向量知识库 (BM25+TF-IDF+FAISS RRF融合)
  - `c_parser.py` - C代码解析器
  - `protocol_parser.py` - 协议文档解析器 (支持PDF表格提取)
  - `protocol_tools.py` - 协议处理工具集
  - `paddleocr_parser.py` - PaddleOCR解析器 (图像文字识别)
  - `log_parser.py` - 日志解析器
  - `rag_engine.py` - RAG引擎和问答代理
  - `intent_classifier.py` - 意图分类器
  - `tool_executor.py` - 统一工具调度器 (支持PDF/MD/Excel表格)
  - `enhanced_rag_engine.py` - 增强RAG引擎 (ReAct+分级检索+语义扩展)
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

- sentence-transformers (可选，用于CrossEncoder rerank)
- SQLite, scikit-learn, faiss-cpu
- pdfplumber, openpyxl, python-docx
- requests

## 模型配置

所有模型在 `config.py` 中配置：

### LLM配置

```python
LLM_PROVIDER = "minimax"  # 可选: minimax/siliconflow/openai
LLM_MODEL = "MiniMax-M2.7"
LLM_MAX_TOKENS = 800
LLM_TEMPERATURE = 0.3
```

### Embedding配置

```python
EMBEDDING_PROVIDER = "tfidf"  # 可选: siliconflow/tfidf
SILICONFLOW_EMBEDDING_MODEL = "BAAI/bge-m3"
SILICONFLOW_VECTOR_DIM = 1024
```

### Rerank配置

```python
RERANK_PROVIDER = "noop"  # 可选: crossencoder/siliconflow/noop
CROSSENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
```

## 检索架构

### 分级检索策略

1. **一级检索（协议优先）**: 精确协议术语（DP ID、命令码）
2. **二级检索（语义扩展）**: 同义词近义词（trip_data, history_record）
3. **三级检索（代码深挖）**: 强制检索代码实现

### 向量检索融合

```
BM25 + TF-IDF + FAISS (FlatIP) → RRF融合 → Rerank重排
```

## 工具管理

所有文档解析工具通过 `models/tool_executor.py` 的 `ToolExecutor` 统一管理。

详见 [工具管理规范](docs/tool_management.md)。

### 新增工具流程

1. 在 `models/tool_executor.py` 中添加解析方法
2. 在 `_register_default_tools()` 中注册
3. 在 `models/__init__.py` 中导出

## 回答模板

最终回答必须包含三要素：

```
[触发机制]
<业务触发条件>

[数据结构]
<数据格式定义>

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

## 回归测试规则

每次代码修改后，**必须**验证以下核心功能正常运作。验证通过方可提交/推送代码。

### 强制验证流程

1. **修改后必查**: 运行 `scripts\verify_api.bat` 或手动验证以下核心API
2. **验证失败禁止提交**: 未通过验证的修改必须修复后才能继续
3. **影响范围自检**: 修改前确认是否影响已有功能

### 核心API检查清单

| 检查项 | API端点 | 预期结果 |
|--------|---------|----------|
| 服务健康 | `GET /api/health` | 返回 `{"status": "ok"}` |
| 文档列表 | `GET /api/labs/kbs/vehiclink-hardware/docs` | 返回非空列表，含protocol_docs |
| 资产列表 | `GET /api/labs/assets` | 返回JSON数组 |
| 分块预览 | `POST /api/labs/assets/chunks/preview` | 返回分块数据 |

### 知识库文档列表 (/api/labs/kbs/<kb_id>/docs)
- **预期**: 返回 `knowledge_base/raw/` 下所有文件（protocol_docs, c_code, logs）
- **验证**: 调用API检查返回的文档数量是否为实际文件系统中的数量
- **禁止**: 仅返回数据库记录或返回空列表
- **状态判断**: 文件存在于 `metadata.db` 的 `knowledge_items` 表 → `indexed`，否则 → `pending`

### 分块预览与导入 (Chunking Preview)
- **预期**: 导入确认页面显示的分块数来自 `/assets/chunks/preview` API 返回的 `data.total`
- **禁止**: 使用前端JS计算的预估分块数（`Math.ceil(text.length / step)`）
- **验证流程**:
  1. 上传文档 → 解析 → 分块配置
  2. 点击"下一步：导入"前，`lastPreviewResult` 必须已缓存API返回结果
  3. 导入确认页的分块数应与预览页的分块数一致

### 文件上传同步
- **预期**: 上传文件自动同步到 `knowledge_base/raw/` 对应分类目录
- **同步规则**:
  - protocol文件 → `knowledge_base/raw/protocol_docs/`
  - C代码文件 → `knowledge_base/raw/c_code/`
  - 日志文件 → `knowledge_base/raw/logs/`
- **验证**: 上传后刷新页面，文档列表应显示新上传的文件

### 重复文件检测
- **预期**: 导入已存在的文件时，前端提示"文件 xxx 已入库，请勿重复添加"
- **实现**: `/assets/chunks` API 通过 `file_content` (base64) 计算MD5查询 `metadata.db`
- **错误码**: `DUPLICATE_FILE` (409 Conflict)

### 语义分块完整性
- **预期**: 语义分块模式必须保留表格和章节不被截断
- **验证**: 预览中表格应作为独立分块，大小可以不同（非固定chunk_size截断）
- **后端实现**: `_split_by_paragraphs()` 按双换行分割，表格用 `[表格 N on Page X]` 标识独立保留

### 5. 破坏性操作必须确认
- **禁止执行**: `git reset --hard`、`git push --force`、`rm -rf`、`git branch -D`
- **数据库删除/迁移**: 操作前必须说明影响范围，经用户确认后再执行
- **force push**: 推送到 main/master 分支前必须用户确认
- **原因**: 破坏性操作难以恢复，可能导致工作丢失或影响他人

### 6. 外部通信需显式授权
- **git push**: 仅在用户明确要求时执行，推送前必须确认目标分支
- **PR创建**: 创建 Pull Request 前必须用户确认标题和内容
- **外部API调用**: 未经用户明确授权，禁止向第三方服务发送数据
- **原因**: 外部通信不可逆，可能产生实际影响

### 7. 范围纪律
- **禁止添加无关功能**: 不得添加与RAG/问答核心无关的模块（如游戏、社交等）
- **禁止引入未讨论技术栈**: 新增依赖需先与用户确认
- **新增文件需相关**: 所有新建文件必须与项目目标（物联网技术支持Agent）相关
- **原因**: 保持项目聚焦，避免复杂度失控

### 8. 变更影响自检
- **修改前确认范围**: 变更前确认是否影响已有API、功能或数据
- **禁止未验证声称**: 不得在未实际运行验证的情况下声称"功能正常"
- **影响报告**: 对已有功能的修改必须在完成后说明影响范围
- **原因**: 防止连锁反应导致其他功能异常

### 9. 确认阈值
- **高风险操作**: 文件删除、数据库迁移、外部通信、权限变更需用户确认
- **中等风险操作**: 多文件修改、大量代码重写、依赖变更需简要说明影响
- **低风险操作**: 单文件内小幅修改、格式化、注释调整可直接执行
- **原因**: 平衡效率与安全，让用户决定何时介入

### 10. 工具调用约束
- **Bash工具**: 仅用于构建、运行测试、git操作等明确任务，禁止复杂管道命令
- **Edit工具**: 需明确指定文件路径和修改内容，禁止模糊批量替换
- **Write工具**: 仅用于新建文件，禁止覆盖未读取的已有文件
- **原因**: 工具能力强大但风险也高，明确用途防止误操作
