# Board Game Platform - 新游戏添加指南 & 前端开发规范

在将新的桌游项目集成到该平台时，为了保证全站用户体验的一致性以及代码的可维护性，请严格遵循以下前后端规范和模板指南。本平台统一采用了 **Apple HIG (Human Interface Guidelines)** 设计风格，并具备全站暗色模式（Dark Mode）与响应式适配能力。

---

## 1. 分层架构与路由管理 (Layered Architecture & Routing)

本项目采用 **三层架构**，所有游戏模块必须遵循此分层规范：

```
接入层 (API Layer)        →  app.py        →  路由注册、请求解析、响应格式化
业务引擎层 (Engine Layer)  →  engine.py     →  游戏规则、状态机、纯计算逻辑
数据访问层 (DAL)           →  database.py   →  统一的异步数据库读写接口
```

1. **接入层 (`app.py`)**：使用 FastAPI 的 `APIRouter` 进行模块化路由注册。每个游戏拥有独立的路由前缀（如 `/cabo/`, `/lasvegas/`）。API 端点**只负责**接收请求、调用引擎层并返回结果，禁止在路由函数中编写业务逻辑。
2. **业务引擎层 (`engine.py`)**：封装具体的游戏规则判定、分数计算等纯逻辑。引擎类不依赖 FastAPI、Socket.IO 或数据库，保持可独立测试。
3. **数据访问层 (`database.py`)**：所有数据库读写操作统一封装为 `async def` 函数。业务代码不应直接编写 SQL，而是调用 `database.py` 中预定义的异步函数。使用 `_get_db()` 上下文管理器统一获取连接。
4. **模块化结构**：每个游戏位于根目录下的独立文件夹（如 `cabo/`），包含 `app.py`（接入层）和 `engine.py`（引擎层）。
5. **路由分配**：在 `main.py` 的 `APPS_CONFIG` 中注册游戏模块。

---

## 1.5 状态管理与实时通信 (State Management & Real-time)

### 持久化数据
对于用户资料、历史战绩等冷数据，使用异步 SQLite (`aiosqlite`)。所有数据库操作通过 `database.py` 统一封装。

### 内存级状态 (Truth State)
对局中的高频变动状态（如手牌、当前回合、场上筹码）通过 `state_store.py` 统一管理：
- **MemoryStore**（默认）：基于 Python `dict` + `asyncio.Lock`，零依赖，适用于单进程开发环境。
- **RedisStore**（生产环境）：设置环境变量 `REDIS_URL` 即可无缝切换，支持多进程/多容器部署。

### WebSocket/Socket.IO 解耦
实时广播服务已独立为**推送网关** (`sio_server.py` 中的 `EventGateway`)：
- 游戏引擎不再直接调用 `sio.emit()`，而是通过 `state_store.publish("game:xxx", event_data)` 发布事件。
- `EventGateway` 订阅各游戏频道，自动向前端触发 `state_update` 事件。
- 若新游戏需要实时推送，只需在 `sio_server.py` 的 `GAME_CHANNELS` 列表中添加频道名。

---

## 2. 前端模板继承 (Frontend Templates Structure)
所有游戏的入口页面（通常为 `index.html` 或 `templates/index.html`）必须**继承 `base.html`**，这样可以自动获得导航栏、Phosphor Icons 图标库以及全局样式（`common.css`）。

**基本骨架模板参考**：
```html
{% extends "base.html" %}

{% block title %}游戏名称 - 一句口号或特色描述{% endblock %}

{% block extra_head %}
<!-- 优先使用 common.css 中已有的全局类，如 .apple-hero, .apple-list 等，尽量少写私有样式 -->
{% endblock %}

{% block content %}
<!-- 全局应用 .apple-hero -->
<div class="apple-hero mb-xl text-center">
    <span class="apple-hero-emoji">🎲</span>
    <h1 class="mb-sm">游戏名称</h1>
    <p class="text-muted" style="font-size: 1.05rem; font-weight: 500;">辅助描述/标语</p>
</div>

<!-- 你的游戏专属 UI 置于此处 -->
<div class="section-title">板块标题</div>
<div class="apple-card">
    ...
</div>

<!-- 强制推荐使用 inline leaderboard 的方式引入历史排行榜 -->
<div id="inline-leaderboard-section">
    <div class="section-title" style="margin-top: var(--space-xl); margin-bottom: var(--space-md);">🏆 历史排行榜</div>
    <div id="histLeaderboard" class="apple-list">
        <!-- JS将动态生成 .apple-list-item 内容覆盖此处 -->
    </div>
</div>
{% endblock %}

{% block extra_body %}
<!-- 游戏的专用 JS 脚本和 Vue 初始化逻辑放在此处，系统已内置 window.showToast() -->
<script>
    // ...
</script>
{% endblock %}
```

---

## 3. UI 组件与 CSS 规范 (Apple HIG CSS Guidelines)
页面元素的开发优先使用 `static/common.css` 中已有的系统变量和工具类，**禁止重新编写重复的自定样式（如圆角、阴影、基础排版等）**。

### 3.1 颜色系统 (Color Variables)
务必通过 CSS variables 调用颜色，确保在深色模式下颜色能够正确映射：
- 背景色：`var(--apple-bg)`, `var(--apple-white)`
- 文本色：`var(--apple-black)`, `var(--apple-gray)`, `var(--apple-secondary-text)`, `.text-muted`
- 主题色系：`var(--apple-blue)`, `var(--apple-green)`, `var(--apple-red)`, `var(--apple-orange)`, `var(--apple-brown)` 等。

### 3.2 布局基础块与排版 (Layout Blocks & Typography)
- **卡片 (`.apple-card`)**：用于承接任何表单、信息汇总和状态反馈容器。包含了圆角 `var(--radius-lg)` 与柔和阴影 `var(--shadow-card)`。
- **标题与间距**：
  - 各大模块的小标题请使用 `<div class="section-title">XXX</div>`。
  - 下边距请统一应用工具类 `.mb-sm`, `.mb-md`, `.mb-lg`, `.mb-xl` 以维持一致的节律 (Spacing)。

### 3.3 交互控件 (Controls)
- **按钮 (`.apple-btn`)**:
  - 必须同时包含基础类 `.apple-btn` 及变体类，如 `.apple-btn-primary` (蓝色主操作), `.apple-btn-success` (绿色确认), `.apple-btn-secondary` (灰色/次要操作), `.apple-btn-danger` (红危险操作)。
  - 需要独占一行时附加 `.apple-btn-block`，大型按钮附加 `.apple-btn-lg`。
- **输入框 (`.apple-input`)**: 圆角、聚焦态符合系统规范。
  - **移动端数字键盘**：当需要录入纯数字（如分数）时，务必加上 `inputmode="numeric" pattern="\d*"` 唤起 iOS/Android 纯九宫格数字键盘，而不是依靠 `type="number"`。
- **开关 (`.apple-switch`)**: 支持双状态布尔切换的界面组件。
- **图标 (Icons)**: 统一使用 Phosphor Icons (`<i class="ph-bold ph-{name}"></i>` 优先用加粗线性图标，或 `<i class="ph-fill ph-{name}"></i>` 充实形体图标)。

---

## 4. 排行榜 (Leaderboards) 开发规范【重点】
无论在本局实时排行榜还是历史数据排行榜，**必须使用全新的 `.apple-list` 组件进行排版**。禁止再使用过时的 Grid-based `.hist-lb-row` 甚至 table。

### 4.1 空白状态防御 (Empty States)
即使数据为空，也应在 `.apple-list` 下保持卡片式边框背景（防止排版坍塌）：

```html
<!-- Vue.js 渲染空状态模板 -->
<div class="apple-list mb-xl">
    <div class="empty-state">
        <span class="empty-icon">👻</span> <!-- 也可用 🏆, 🃏, 等贴合主题的表情 -->
        还没人玩过呢，快去开一局！
    </div>
</div>
```

### 4.2 排行榜列表项渲染 (List Item Structure)
数据列表渲染应使用 `.apple-list-item` 为基础包裹。名次使用 `rank-*` 类标识金、银、铜牌及普通名次，并用 Flex 拆分出右对齐的数据统计（Stat Badges）。

**原生 JS（或 Vue `v-for`）模板标准结构：**
```javascript
// JS拼接模板示例
data.leaderboard.forEach((p, idx) => {
    const rank = idx + 1;
    // 使用全局统一定义的 rank-* CSS工具类
    let rankClass = rank === 1 ? 'rank-1' : (rank === 2 ? 'rank-2' : (rank === 3 ? 'rank-3' : 'rank-other'));
    let rankIcon = rank === 1 ? '👑' : rank;

    html += `
        <div class="apple-list-item">
            <!-- 1. 左侧名次/奖牌 -->
            <div class="rank-num ${rankClass}">${rankIcon}</div>
            
            <!-- 2. 中间玩家信息 -->
            <div class="apple-list-item-content">
                <div class="apple-list-item-title">${p.name}</div>
                <!-- 附属统计信息可用 .history-trail 工具类并调整透明度或字号 -->
                <div class="history-trail">${p.total_games}局 · 胜率${p.win_rate}%</div>
            </div>
            
            <!-- 3. 右侧并排数值统计区 -->
            <div style="text-align: right; display: flex; align-items: center; gap: 16px;">
                <div style="text-align: right; width: 60px;">
                    <div class="history-trail" style="font-size: 0.7rem; margin-bottom: 2px;">爆牌数</div>
                    <!-- 使用不同的苹果主题色 -->
                    <div class="score-badge" style="font-size: 1.1rem; color: var(--apple-red);">${p.total_busts}</div>
                </div>
                <div style="text-align: right; width: 60px;">
                    <div class="history-trail" style="font-size: 0.7rem; margin-bottom: 2px;">场均得分</div>
                    <div class="score-badge" style="font-size: 1.2rem; color: var(--apple-blue);">${p.avg_score}</div>
                </div>
            </div>
        </div>
    `;
});
```

---

## 5. 常见注意事项与避坑指南 (Caveats)
1. **暗色模式陷阱**：遇到白底黑字在暗色模式下不可见的 Bug 时，一般是开发者误写了内联样式 `style="background: white; color: black;"`，应全部替换为 `background: var(--apple-white); color: var(--apple-black)`！
2. **样式重复**：如果发现一个元素的 CSS 书写了繁琐的圆角、阴影配置（如 `border-radius: 12px; box-shadow: ...`），第一时间考虑它是不是属于全局的 `.apple-card` 或 `.apple-list`，应该通过公用类重构。
3. **安全注入**：在原生 JS 通过 `innerHTML` 渲染列表时，涉及到玩家昵称 `p.name` 必须经过 `escHtml()` 等函数转义，避免 XSS。如果使用 Vue.js (`{{ p.name }}`) 则自动转义，无需操心。
4. **弹窗（Modal/Toast）**：全站禁止使用浏览器自带原生的 `alert()` 或 `confirm()` 阻断页面操作（除非特意声明危急情况）。**强烈建议调用全局已封装的 `window.showToast(message, type)` 进行轻量提示**，亦可自己编写叠加层的 `.apple-modal` 风格弹窗进行二次确认询问。
5. **禁用状态（Disabled）**：表示不可用、维护中的游戏卡片或按钮等，建议通过降低透明度（如 `.disabled` 类的 `opacity: 0.5` 与浅色背景融合）来实现，并且一定要移除悬浮放大和投影交互（`box-shadow: none`, `cursor: not-allowed`）。避免使用高强度的全局 `filter: grayscale(100%)` ，否则视觉上容易产生生硬的“系统故障感”。
6. **Vue 与内联 SVG 的包含关系**：由于部分游戏页面使用了 Vue 3（如被 `<div id="app">` 包裹），Vue 的模板编译器在解析 DOM 时会主动剥离并忽略所有的内部 `<style>` 标签。如果你使用 Jinja2 注入包含动态动画或特殊字体的 SVG，请务必将 SVG 的专属 CSS（如 `@keyframes`, `@import url(...)`）写在页面顶层的 `{% block extra_head %}` 之中，切忌直接写在 SVG 文件内部的 `<style>` 里，否则会导致动画静止及字体渲染失败。

---

## 6. 新游戏接入检查清单

本项目采用 **三层架构 (API → Engine → DAL) + 事件驱动推送** 模式。在添加新游戏时，请遵循以下检查清单。

**1. 模块结构 (Module structure)**

* 在根目录下创建游戏文件夹（如 `yourgame/`），包含以下文件：
  - `app.py`：接入层 — 路由定义、请求解析、调用引擎、返回结果
  - `engine.py`：引擎层 — 纯游戏逻辑、数据模型、状态操作
  - `index.html`：前端页面
  - `__init__.py`：空文件（使其成为 Python 包）

**2. 引擎层规范 (Engine pattern)**

* `engine.py` 中定义 `GameState` 类和 `YourGameEngine` 类。
* 引擎类的方法只操作传入的 `GameState` 对象，不依赖 FastAPI/Socket.IO/数据库。
* 引擎方法返回结果字典，不抛出 HTTP 异常。

**3. 路由层规范 (Router pattern)**

* 在 `app.py` 中使用 `router = APIRouter(prefix="/yourgame", tags=["YourGame"])`。
* 不要为游戏模块创建子 `FastAPI()` 应用。
* 导出的变量名必须是 `router`（供 `main.py` 的动态加载器使用）。
* 路由函数只做：解析请求 → 加锁 → 调用引擎 → 发布事件 → 返回结果。

**4. 在主应用中注册 (Register in main app)**

* 在 `APPS_CONFIG` 中添加映射，例如：`"yourgame": "yourgame.app"`。
* 如果需要静态文件，请在 `main.py` 中显式挂载到最终的带前缀的路径上。

**5. 数据库规范（仅限异步）**

* `database.py` 中的 API 均为异步函数；所有调用都必须使用 `await`。
* 使用 `_get_db()` 上下文管理器获取连接，不要直接使用 `aiosqlite.connect()`。
* 在 `init_db()` 中添加新游戏的 `CREATE TABLE IF NOT EXISTS` 语句。

**6. 状态管理与实时推送 (State & real-time)**

* 如需实时推送，通过 `state_store.publish("game:yourgame", event_data)` 发布事件。
* 在 `sio_server.py` 的 `EventGateway.GAME_CHANNELS` 中添加 `"game:yourgame"`。
* 不要在游戏模块中直接调用 `sio.emit()`。

**7. 生命周期、导入、前端规范**

* 不要在模块导入时调用 `init_db()`，数据库初始化已集中在 lifespan 中处理。
* 使用标准导入 `import database` 或 `from yourgame.engine import ...`，禁止 `sys.path.insert`。
* 前端使用 `const API_BASE = '/yourgame/api'`，保持页面路由与 API 前缀对齐。

**8. 合并前的快速检查 (Pre-merge quick checks)**

* `python -m compileall .` 编译通过。
* `/docs` (Swagger UI) 中可正常看到新游戏的 API 端点。
* 核心 API（如 `/api/status`、`/api/leaderboard` 以及写入接口）测试正常。
* 已在首页和游戏列表中添加了入口。

---

## 7. PWA (渐进式 Web 应用) 支持
桌游助手现已全面支持 PWA！你可以直接在手机浏览器（如 Safari 或 Chrome）中选择“添加到主屏幕”。
- **沉浸式体验**：从主屏幕启动时，将完全隐藏浏览器的地址栏与底部导航条，呈现纯净的全屏应用界面。
- **类原生质感**：配合 Apple HIG 设计规范和全局的平滑转场动画，体验将和原生的 iOS App 完全一致。
- **配置资源**：相关的 `manifest.json` 与 PWA 图标均已存放于 `static/icons` 和 `static` 目录下，所有页面通过 `base.html` 中心化接入，无缝兼容所有子游戏。

---

## LasVegas Recent Architecture Updates

- Added Socket.IO state broadcasting for LasVegas state mutations (`add_player`, `remove_player`, `add_bill`, `remove_bill`, `setup_field`, `end_game`, `reset`), emitting `state_update`.
- Moved field setup randomization into backend truth state:
  - New API: `POST /lasvegas/api/setup_field`
  - New API: `GET /lasvegas/api/field`
  - `GET /lasvegas/api/status` now includes `field`.
- Frontend LasVegas page now uses Alpine.js for reactive leaderboard/player/history rendering, reducing `innerHTML` string rendering in core views.
