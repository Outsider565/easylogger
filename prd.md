# EasyLogger PRD (MVP)

## 1. Background
EasyLogger 是团队内部使用的最小化日志查看工具。
MVP 目标是：
- 以尽量少的安装和配置成本，扫描项目目录中的结构化 JSON 日志。
- 在网页端以表格方式展示数据。
- 引入 `view` 概念，把“怎么展示数据”与“原始数据”解耦并可持久化。

## 2. Product Goals
### 2.1 目标
- 安装简单：单一语言主栈（Python + React），命令启动即可使用。
- 代码简单：功能聚焦，避免过早设计复杂能力。
- 支持扩展：后续可新增日志类型、更多 view 能力。

### 2.2 非目标（MVP 不做）
- 多用户协作、权限、登录体系。
- 安全隔离（团队内部使用，不做表达式沙箱）。
- 实时日志监听（日志扫描为一次性触发）。
- 缓存层（每次手动刷新时全量扫描）。

## 3. Core Concepts
### 3.1 Project Root
用户传入的项目根目录（`<root>`）。所有扫描、view 读取、路径展示都基于它。

### 3.2 Data Record
单个 JSON 文件解析得到的一行数据。

### 3.3 Primary Key
主键为 JSON 文件相对 `project root` 的路径（例如 `experiments/run1/result.scaler.json`）。

### 3.4 View
View 定义“如何展示数据”，包括：
- 列顺序
- 隐藏列
- 列别名（alias）
- 表达式列（单行 Python 表达式）
- 行置顶（pinned IDs）
- 其余行排序规则

View 与项目绑定，存储在：
- `<root>/.easylogger/views/<name>.json`

## 4. Data Source and Scan Rules
### 4.1 扫描范围
- 对 `<root>` 做递归扫描。
- 默认忽略目录：`.git`, `node_modules`, `.venv`。

### 4.2 文件匹配
- 用户通过命令行传入 regex（替代 glob）。
- create 时写入 view 配置。
- 后续 view 时读取该 view 中的 regex。

### 4.3 首个支持的数据类型：scaler
MVP 仅支持“扁平 JSON 对象”：
- 允许 value 类型：`string | number | boolean | null`
- 不允许数组和对象（遇到则按宽松策略处理）

示例：
```json
{
  "step": 1200,
  "loss": 0.238,
  "lr": 0.0001,
  "phase": "train",
  "success": true,
  "note": null
}
```

### 4.4 宽松解析策略
- 文件级错误（非法 JSON、无法读取）：跳过并记录 warning。
- 字段级问题（如数组/对象值）：该字段置空并记录 warning。
- 最终扫描不中断。

## 5. CLI Design
### 5.1 创建 view
```bash
easylogger create <root> --pattern "<regex>" --name "view1"
```
行为：
- 创建 `<root>/.easylogger/views/view1.json`
- 立即执行一次扫描
- 输出：summary + 前 N 条 warning（N 可配置，默认 20）

### 5.2 打开 view（启动 Web）
```bash
easylogger view <root> --name "view1"
```
行为：
- 读取 `<root>/.easylogger/views/view1.json`
- 启动本地 Web 服务并打开页面

### 5.3 默认 view（可选）
```bash
easylogger view <root>
```
- 支持默认 view（例如 `default`）
- 若找不到 view：报错并提示使用 `create` 创建

### 5.4 错误提示要求
当 view 不存在时，错误信息应明确包含：
- 当前 root 路径
- 缺失的 view 名称
- 建议命令：`easylogger create <root> --pattern "..." --name "..."`

## 6. Web MVP Requirements
### 6.1 数据展示
- 表格展示扫描结果。
- 所有 key 自动成为列。
- 缺失字段显示 `null`。

### 6.2 Refresh 机制
- 不自动刷新。
- 用户手动点击 Refresh 才重新扫描。
- Refresh 的唯一职责是触发“重新扫描文件系统”；其余 UI 操作不应要求用户手动 Refresh。

### 6.3 View 编辑能力
- 顶部提供 view 标签栏（类似浏览器 tab），可切换当前 view。
- 标签栏最右侧提供 `+` 新建 view，支持从已有 view 复制配置（通过下拉选择源 view）。
- 每个 view 支持重命名。
- 调整列顺序（支持拖拽排序）。
- 隐藏/显示列。
- 提供批量显隐（All visible / All invisible）。
- 设置列 alias。
- 设置列显示格式（format）。
- 新建表达式列。
- 在表格中对任意行执行 Pin / Unpin（不再通过独立 Rows 面板配置）。
- 对已 pinned 的行支持拖拽调整 pinned 内部顺序。
- 在表头点击列名切换排序方向（asc / desc），并显示箭头状态。
- 保存到 view 文件。

### 6.4 表达式列规则
- 单行 Python 表达式。
- 列引用语法：`row["col_name"]`。
- 可使用 Python 内置能力（MVP 不做安全限制）。
- 计算失败时，该单元格展示错误字符串。

### 6.4.1 列格式规则（新增）
- 每列可选配置 `format`，语法为 Python `str.format` 模板，变量名固定为 `d`。
- 示例：`"{d:02}"`、`"{d:.3f}"`、`"{d:,}"`。
- 格式应用仅影响展示值，不影响排序逻辑（排序仍基于原始值）。
- 若格式执行失败，该单元格展示 `FORMAT_ERROR: ...`。
- 修改格式模板后，应在当前已扫描数据上实时预览生效（无需手动 Refresh）。
- `Format` 列标题在 hover 时应显示帮助提示，说明语法与示例。

### 6.5 行排序规则
- `pinned_ids` 对应行固定在最前。
- pinned 行之间顺序由用户拖拽决定。
- 其余行按指定字段排序。
- 排序交互来自表头点击；pinned 行不受普通排序影响。
- 若排序值为字符串数字（如 `"12"`），自动按数值参与排序。

### 6.6 约束
- alias 不允许重名；冲突时禁止保存并报错。
- hidden 列仍可被表达式列引用。
- 编辑未保存时离开页面，需要提示（unsaved changes warning）。
- 页面在宽屏下应保持自适应布局，避免固定窄宽度导致大量留白。

## 7. View File Schema (MVP Draft)
```json
{
  "name": "view1",
  "pattern": ".*\\.scaler\\.json$",
  "columns": {
    "order": ["path", "step", "loss", "lr"],
    "hidden": ["note"],
    "alias": {
      "lr": "learning_rate"
    },
    "format": {
      "step": "{d:04}",
      "loss": "{d:.3f}"
    },
    "computed": [
      {
        "name": "loss_x_step",
        "expr": "row[\"loss\"] * row[\"step\"]"
      }
    ]
  },
  "rows": {
    "pinned_ids": [
      "experiments/run_001/result.scaler.json"
    ],
    "sort": {
      "by": "loss",
      "direction": "asc"
    }
  }
}
```

说明：
- MVP 不写 `version` 字段。
- 后续若 schema 有变更，再引入版本升级机制。

## 8. Technical Architecture
### 8.1 Tech Stack
- Backend/API/CLI: Python + FastAPI + Typer
- Frontend: React

### 8.2 模块划分
- `scanner`：递归扫描 + regex 匹配 + JSON 宽松解析
- `view_store`：读写 `<root>/.easylogger/views/*.json`
- `view_engine`：列转换、表达式列、排序/pin
- `web_api`：前端数据接口（scan、load/save view）
- `frontend`：表格展示与 view 编辑 UI
  - 前端资源采用多文件组织（`index.html` + `styles.css` + `app.jsx`），避免单文件过大难维护

### 8.3 扩展策略
- 后续数据类型扩展为 parser 插件（先 scaler，后续可新增类型）。
- 前后端接口稳定，支持前端复杂化演进。

## 9. MVP Acceptance Criteria
1. 可通过 `easylogger create <root> --pattern ... --name ...` 创建 view 并完成首次扫描。
2. 可通过 `easylogger view <root> --name ...` 打开网页并手动 Refresh 数据。
3. 可在网页中编辑并保存列顺序、hidden、alias、表达式列。
4. 可配置并持久化 `pinned_ids` 与普通排序规则。
5. Web 支持多 view 标签切换、复制新建和重命名，并正确持久化到 view 文件。

## 10. Open Questions (Post-MVP)
- 是否支持多 regex 规则组合。
- 是否引入扫描缓存提升大项目性能。
- 是否在表达式执行中引入安全沙箱。
- 是否支持更多日志结构（嵌套 JSON、数组、JSONL）。

## 11. Testing Requirements (Added)
- 使用 `pytest` 作为统一测试框架，覆盖 scanner / view_store / view_engine / web_api / cli。
- 增加前端 E2E 测试（基于 Playwright），至少覆盖：
  - 手动 `Refresh` 触发重新扫描。
  - `Save View` 后配置落盘。
  - `unsaved changes` 状态下离开页面提示逻辑。
  - 列配置（alias / hidden / computed）可编辑并持久化。
  - 列格式配置（format）可编辑并持久化，并在表格内正确显示。
  - 至少覆盖多种格式模板（补零、浮点精度、百分比、千分位）及格式错误场景。
  - `Format` hover 帮助提示可见。
  - view 标签栏的切换、复制新建、重命名流程可生效并持久化。
  - 表格内的 Pin / Unpin、pinned 拖拽重排、表头排序交互可生效并持久化。
