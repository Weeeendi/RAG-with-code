# 工具管理规范

## 1. 概述

所有Agent工具通过统一的 `ToolExecutor` 类进行注册和调度，确保工具管理一致性和可扩展性。

## 2. 核心组件

### ToolRegistry
工具注册中心，管理所有可用工具。

```python
class ToolRegistry:
    _tools: Dict[str, Callable] = {}           # 工具名称 -> 处理函数
    _extensions: Dict[str, str] = {}            # 文件扩展名 -> 工具名称
```

### ToolExecutor
统一的工具调度器，负责执行具体工具。

```python
class ToolExecutor:
    def execute(self, file_path: str, tool_name: str = None, **kwargs) -> ToolResult
```

### ToolResult
工具执行结果容器。

```python
@dataclass
class ToolResult:
    success: bool
    data: Any
    error: Optional[str] = None
```

## 3. 注册新工具

### 方式一：静态注册
```python
from models import ToolExecutor

executor = ToolExecutor()
executor.register_tool(
    name='markdown',                           # 工具名称
    handler=my_markdown_parser,                # 处理函数
    extensions=['.md', '.markdown']            # 支持的扩展名
)
```

### 方式二：直接在 ToolExecutor 子类中注册
```python
class MyToolExecutor(ToolExecutor):
    def _register_default_tools(self):
        super()._register_default_tools()
        self.registry.register('custom', self._parse_custom, ['.custom'])
```

## 4. 工具调度规则

1. **按扩展名自动调度**：调用 `execute(file_path)` 时根据文件扩展名自动选择工具
2. **手动指定工具**：调用 `execute(file_path, tool_name='pdf')` 可强制使用指定工具
3. **错误处理**：工具执行失败返回 `ToolResult(success=False, error=...)`

## 5. 内置工具

| 工具名称 | 支持扩展名 | 依赖库 | 表格支持 |
|---------|-----------|--------|---------|
| pdf | .pdf | pdfplumber | ✅ extract_tables() |
| docx | .docx, .doc | python-docx | - |
| excel | .xlsx, .xls | openpyxl | ✅ 原生表格 |
| txt | .txt | - | - |
| md | .md | - | ✅ 正则解析表格 |

## 6. 新增文档类型流程

1. 在 `models/tool_executor.py` 中添加解析方法
2. 在 `_register_default_tools()` 中注册
3. 在 `__init__.py` 中导出

## 7. 示例

```python
from models import ToolExecutor

executor = ToolExecutor()

# 自动调度
result = executor.execute("document.pdf")
# 返回: {'page': 1, 'text': '...', 'tables': [[...]]}

# 手动指定
result = executor.execute("document.pdf", tool_name="pdf")

# 注册新工具
def parse_md(file_path, **kwargs):
    with open(file_path) as f:
        return ToolResult(success=True, data=f.read())

executor.register_tool('markdown', parse_md, ['.md'])
```

## 8. 表格解析返回值格式

### PDF表格

```python
{
    'page': 1,
    'text': '页面文本内容',
    'tables': [
        [['单元格1', '单元格2'], ['单元格3', '单元格4']],
        ...
    ]
}
```

### Markdown表格

```python
{
    'page': 1,
    'text': 'Markdown文本（包含表格内容）',
    'tables': ['| Col1 | Col2 |\n| --- | --- |\n| val1 | val2 |', ...]
}
```

## 9. 注意事项

- 所有文档解析必须通过 `ToolExecutor`，禁止直接 import 解析库
- 解析库（如 pdfplumber）在工具方法内延迟导入
- 工具执行结果统一使用 `ToolResult` 封装
- 表格数据通过 `tables` 字段返回，protocol_parser.py 中的 `_process_tables()` 负责转换为文本块
