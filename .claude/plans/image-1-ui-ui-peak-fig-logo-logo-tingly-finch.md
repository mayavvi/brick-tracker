# Plan: 文件预览 & 比对模块（File Compare）

## Context

`/file-compare` 当前仅是占位页（`templates/file_compare.html:1-17`）。用户希望把它做成一个**类 git 的程序比对工具**，痛点是程序文件散落在深层目录里（每个 study 下有 task/dryrun/dsur/smc 等，每层还有 prog/sdtm、prog/tables、qcprog/compare 等子目录），一次可能面对上百个 `.sas / .log / .lst` 文件。三个核心能力：

1. **版本快照（单文件版本追踪）** —— 用户点按钮，把当前程序内容"打卡"入库；下次再打卡时可 diff 两次打卡间的改动。
2. **双文件对比** —— 不同 task 下的同名（或不同名）程序并排 diff，直观高亮增删。
3. **Main vs QC 时间校验** —— 扫描某 study 所有 main/qc 程序的 `.log`，列出 QC log 时间早于 Main log 的任务（说明 QC 还没跟上）。

**硬约束（贯穿整个方案）**：所有预览 / 对比操作**一律只用 `Path.read_bytes()`**，绝不用任何需要写锁或需 SAS 进程参与的方式打开文件 —— 用户在 SAS EG / Enterprise Guide 里保持对原始文件的编辑权不受影响。

---

## 数据模型

### 新表 `file_snapshots`（`database.py` schema 追加）

```sql
CREATE TABLE IF NOT EXISTS file_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT NOT NULL,
    abs_path     TEXT NOT NULL,          -- 规范化后的绝对路径（作为文件身份）
    study_id     TEXT NOT NULL DEFAULT '',
    content_hash TEXT NOT NULL,          -- sha256，去重用
    content      TEXT NOT NULL,          -- 解码后的文本（SAS 文件通常 <200KB，直接存）
    encoding     TEXT NOT NULL,          -- 'utf-8-sig' / 'gbk' / 'cp936' / ...
    size_bytes   INTEGER NOT NULL,
    note         TEXT NOT NULL DEFAULT '',
    snapshot_ts  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snap_path ON file_snapshots(abs_path, snapshot_ts DESC);
CREATE INDEX IF NOT EXISTS idx_snap_user ON file_snapshots(username, snapshot_ts DESC);
```

**去重逻辑**：打快照前先查同路径最新记录的 `content_hash`，相同则返回旧记录、不写新行。

### Pydantic models（`models.py` 追加）

```python
class FileEntry(BaseModel):
    abs_path: str
    rel_path: str            # 相对 PROJECTS_BASE_PATH，前端展示用
    study_id: str
    task: str                # task/dryrun/dsur/smc/... 一级子目录
    role: Literal["main", "qc", "unknown"]
    kind: Literal["sas", "log", "lst", "other"]
    size: int
    mtime: float

class FileSnapshot(BaseModel):
    id: int
    abs_path: str
    content_hash: str
    size_bytes: int
    note: str
    snapshot_ts: datetime

class DiffLine(BaseModel):
    op: Literal["equal", "insert", "delete", "replace"]
    a_lineno: int | None
    b_lineno: int | None
    a_text: str = ""
    b_text: str = ""

class QcTimingRow(BaseModel):
    task: str
    program: str             # 程序基名（dm / ae / adae …）
    main_log_mtime: datetime | None
    qc_log_mtime: datetime | None
    stale: bool              # qc_log < main_log
    reason: str              # 'qc-older' / 'qc-missing' / 'ok'
```

---

## 服务层（新文件）

### `services/file_index.py` — 程序索引 + 搜索

解决"上百个文件"的搜索痛点。启动成本换查询速度。

- `build_index(study_id) -> list[FileEntry]` —— 对单个 study 做一次 `Path.rglob("*.sas") / *.log / *.lst`，识别 role（路径包含 `qcprog` / `qc` → qc，其余 → main），kind 按后缀。结果放 TTL 缓存（复用 `_StudyDirectoryCache` 模式，`services/scanner.py:24-55`）。
- `search(query, study_id=None, kind=None, role=None, limit=100)` —— 对索引做子串 + subsequence 匹配（复用 `scanner.py:93-100` 的 `_matches` / `_is_subsequence`），按 mtime 倒序返回前 100 条。
- `get_tree(study_id) -> dict` —— 按 `task → folder → files` 两级嵌套的字典，前端画懒加载树。

### `services/file_reader.py` — 安全读取

- `read_text(abs_path, max_bytes=2_000_000) -> (text, encoding)` —— `Path.read_bytes()` 后依次尝试 `utf-8-sig / utf-8 / gbk / cp936 / latin-1`；超限返回前 N 字节 + 截断标记。**不开写句柄**。
- `read_log_page(abs_path, offset=0, lines=500)` —— 大 log 分页（按行切）。
- `sha256_bytes(data)` —— 给 snapshot 用。
- 路径合法性校验：必须位于 `PROJECTS_BASE_PATH` 下（`abs_path.resolve().is_relative_to(PROJECTS_BASE_PATH)`），防目录穿越。

### `services/file_diff.py` — 结构化 diff

- `diff_texts(a: str, b: str) -> list[DiffLine]` —— 基于 `difflib.SequenceMatcher`，输出带 op + 双边行号的扁平数组。前端照此画左右对照。
- 空白 / 大小写不敏感开关（参数）。
- 可选 `mode="unified"` 复用 `difflib.unified_diff` 生成单栏视图。

### `services/qc_timing.py` — main/qc 时序校验

- `check_study(study_id) -> list[QcTimingRow]`
  - 用 `file_index` 拿到所有 `.log`
  - 按**程序基名 + task** 配对：main 侧 `prog/**/dm.log` ↔ qc 侧 `qcprog/**/dm.log`
  - 比较 `mtime`（v1 就用文件 mtime，够用；v2 可升级到解析 log 里的 `real time` 时间戳）
  - 结果：`stale=True` 当 `qc_log_mtime < main_log_mtime` 或 `qc_log` 缺失

---

## API 路由（新文件 `routers/file_compare.py`）

挂 `/api/files` 前缀：

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/files/tree?study_id=` | 树形视图（懒加载） |
| GET | `/api/files/search?q=&study_id=&kind=&role=&limit=` | 扁平搜索 |
| GET | `/api/files/preview?path=` | 预览文件（文本+编码） |
| GET | `/api/files/log-page?path=&offset=&lines=` | 大 log 分页 |
| POST | `/api/files/snapshot` body `{path, note?}` | 打快照 |
| GET | `/api/files/snapshots?path=` | 列出某路径全部快照（新→旧） |
| GET | `/api/files/diff` params `a_path` / `a_snap_id` + `b_path` / `b_snap_id` | 统一 diff 入口，两端各自可为"当前文件"或"历史快照" |
| GET | `/api/files/qc-timing?study_id=` | QC 时序表 |

所有端点 `Depends(get_current_user)`，并在 main.py 挂载（`main.py:104-114` 附近加一行）。

---

## 前端（整页重写 `templates/file_compare.html`）

单页三 Tab（Alpine.js `x-data="fileCompareApp()"`，复用 `tracker.html` 的模式）：

```
┌─ 顶栏：study 选择器 + 全局搜索框 ─────────────────────┐
│ [浏览预览] [程序对比] [QC 时间检查]                   │
└──────────────────────────────────────────────────────┘
```

### Tab 1 · 浏览预览（主力功能）

左侧 **搜索+树形导航**（30% 宽）：
- 顶部搜索框，300ms 防抖；输入时切到扁平搜索结果视图；清空回到树
- 筛选药丸：`.sas` / `.log` / `.lst` / main / qc
- 树：study → task（task / dryrun / dsur / smc …）→ 子目录 → 文件。懒加载，点击才 fetch 下一层
- 每个文件行显示：kind 色标 + 文件名 + 灰色 mtime
- "最近预览"板块（localStorage 记 10 条）固定在最上

右侧 **预览面板**（70% 宽）：
- 顶栏：路径面包屑 + `📸 打快照`按钮 + `📜 历史` 抽屉开关
- 正文：`<pre>` 等宽显示源码，行号在左侧 gutter；`.log` 超 2000 行时分页按钮（上/下 500 行）
- 历史抽屉：列出该文件所有快照 `#3 · 4/23 14:22 · yawei · note...`；每条右侧 `对比当前` 按钮 → 跳到 Tab 2 预填

**非破坏性提示**：预览面板右下角一行灰字 `// 只读模式 · 原文件仍可在 SAS 中编辑`。

### Tab 2 · 程序对比

两栏"文件槽"：
- **A 侧**：按钮 `+ 选文件` / `+ 选快照` → 弹出跟 Tab 1 同款的搜索树抽屉
- **B 侧**：同上
- 选完两端后，主区域画 diff：
  - 默认 side-by-side（左右两栏，行号独立，`insert` 绿底 / `delete` 红底 / `replace` 紫底高亮）
  - 顶部切换 `side-by-side | unified`
  - 顶部开关 `忽略空白` / `忽略大小写`
  - 顶部统计条：`+42 行 / -17 行 / 3 处修改`

### Tab 3 · QC 时间检查

- 顶部 study 选择器（或复用顶栏的）
- 下方致密表格：`Task | Program | Main Log | QC Log | 状态`
- `stale` 行品红高亮；`qc-missing` 行显示 `—` + 黄色标记
- 每行 `Program` 列可点击 → 跳到 Tab 2 并预填 main.sas / qc.sas 做比对

### 空态 / 技术化文案
- 未选 study：`// 先选个 study，然后让我们看看里面都藏了什么`
- 搜索无结果：`// 没找到。换个关键字或者去掉筛选器试试`
- QC 检查全通过：`// 全部 qc log 都晚于 main log。干净。`

---

## 修改/新增文件清单

| 文件 | 改动 |
|---|---|
| `database.py` | 在 `_SCHEMA_SQL` 追加 `file_snapshots` 表 |
| `models.py` | 加 `FileEntry` / `FileSnapshot` / `DiffLine` / `QcTimingRow` |
| `services/file_index.py` | **新** — 索引 + 搜索 + 树 |
| `services/file_reader.py` | **新** — 安全读取 + 编码探测 + 分页 |
| `services/file_diff.py` | **新** — difflib 包装，返回结构化 diff |
| `services/qc_timing.py` | **新** — main/qc log 时序比对 |
| `routers/file_compare.py` | **新** — 上述 8 个端点 |
| `main.py` | `from routers import file_compare` + `include_router` |
| `templates/file_compare.html` | 整页重写（三 Tab + Alpine 组件） |

## 复用点

- `discover_studies(PROJECTS_BASE_PATH)` — `services/scanner.py:79`，拿 study 列表
- `_StudyDirectoryCache` 的 TTL 缓存模式 — `services/scanner.py:24-55`，照抄给 `file_index`
- `_is_subsequence` / `_matches` — `services/scanner.py:93-100`，直接用
- `auth.get_current_user` — 所有端点加 `Depends`
- 前端 Alpine 模式（tag 输入、抽屉、防抖搜索、`x-transition`） — `templates/tracker.html` / 新版 `me.html`
- Tailwind neon/warm 色调 + cfx-corners 圆角边框样式 — `base.html` 已就绪

## 验证

1. `uvicorn main:app --reload` 启动
2. **预览**：`/file-compare` → 选 study → 树形展开到某 `.sas` → 右侧正常显示源码 + 行号；打开 SAS EG 确认**原文件仍可编辑保存**
3. **快照**：点 `📸 打快照` → 历史抽屉出现一条；编辑原文件保存后再点一次 → 抽屉出现第二条，hash 不同
4. **单文件版本 diff**：抽屉里点第一条的 `对比当前` → Tab 2 高亮第二次的改动
5. **双文件 diff**：Tab 2 分别选 `task/prog/tables/t_ae.sas` 和 `dryrun/prog/tables/t_ae.sas` → 高亮行级差异
6. **搜索**：顶栏输入 `adae` → 跨所有 task 返回 ≤100 条命中，mtime 倒序
7. **QC 时间检查**：Tab 3 选某 study → 若 `dryrun/prog/sdtm/dm.log` 比 `qcprog/sdtm/dm.log` 新，则该行品红高亮
8. **非破坏性回归**：在 SAS 中打开某 `.sas` 并保存 → `/file-compare` 预览仍能读到最新内容，保存过程未被拒（app 没拿写锁）
9. **安全**：尝试 `GET /api/files/preview?path=C:/Windows/System32/drivers/etc/hosts` → 拒绝（路径不在 `PROJECTS_BASE_PATH` 下）
10. **大文件**：预览一个 >10MB 的 `.log` → 走分页接口，首屏 500 行，翻页正常

## 分阶段实施建议（方便分 PR）

- **P1 基础读 + 预览**：`file_reader` + `file_index` + `tree/search/preview` 端点 + Tab 1 —— 能看就行
- **P2 快照 + 单文件 diff**：`file_snapshots` 表 + snapshot/diff 端点 + 历史抽屉
- **P3 双文件 diff**：Tab 2 完整功能
- **P4 QC 时序**：`qc_timing` 服务 + Tab 3

## 方案位置

本方案文件：`C:\Users\34755\.claude\plans\image-1-ui-ui-peak-fig-logo-logo-tingly-finch.md`
