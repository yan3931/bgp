# Board Game Platform - 新游戏添加指南 & 前端开发规范

在将新的桌游项目集成到该平台时，为了保证全站用户体验的一致性以及代码的可维护性，请严格遵循以下前后端规范和模板指南。本平台统一采用了 **Apple HIG (Human Interface Guidelines)** 设计风格，并具备全站暗色模式（Dark Mode）与响应式适配能力。

---

## 1. 目录及架构要求 (Directory & Architecture)
1. **模块化结构**：每个游戏应作为一个独立的 Python/Flask 蓝图（Blueprint）或独立的路由模块建立，目录需位于根目录下（如 `cabo/`、`lasvegas/`、`Avalon/` 等）。
2. **路由分配**：在 `main.py` 内注册该游戏专属路由，并在首页 `gamelist.html` (`index.html`) 的游戏列表中添加对应入口与规则描述。
3. **数据分离**：涉及游戏战绩、胜率数据的读取与写入，统一复用和扩展 `database.py` 中已封装的数据库操作逻辑，避免在各游戏的 `app.py` 中直接拼写重复 SQL 获取跨游戏的公共数据接口（如排行榜接口需保持输出格式的一致）。

---

## 2. 前端模板继承 (Frontend Templates Structure)
所有游戏的入口页面（通常为 `index.html` 或 `templates/index.html`）必须**继承 `base.html`**，这样可以自动获得导航栏、Phosphor Icons 图标库以及全局样式（`common.css`）。

**基本骨架模板参考**：
```html
{% extends "base.html" %}

{% block title %}游戏名称 - 一句口号或特色描述{% endblock %}

{% block extra_head %}
<style>
    /* 此处仅编写该游戏独有或覆盖性的样式。禁止反复定义通用工具类！ */
    .hero-h1 {
        background: linear-gradient(135deg, #FF9500, #FFCC00);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
</style>
{% endblock %}

{% block content %}
<div class="apple-hero mb-xl text-center">
    <h1 class="hero-h1 mb-sm"><span style="font-size: 1.2em;">🎲</span> 游戏名称</h1>
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
    <div id="histLeaderboard">
        <!-- JS将动态生成内容覆盖此处 -->
    </div>
</div>
{% endblock %}

{% block extra_body %}
<!-- 提示框组件 -->
<div id="toast" class="toast"></div>

<!-- 游戏的专用 JS 脚本和 Vue 初始化逻辑放在此处 -->
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
4. **弹窗（Modal）**：全站禁止使用浏览器自带原生的 `alert()` 或 `confirm()` 阻断页面操作（除非特意声明），推荐调用全站封装好的 `Toast` 提示功能，亦可自己编写叠加层的 `.apple-modal` 风格弹窗进行询问操作。

---

## 6. 新游戏接入检查清单

本项目现已全面采用 `APIRouter + include_router + 异步数据库 (aiosqlite)` 架构。在添加新游戏时，请遵循以下检查清单。

**1. 路由模式 (Router pattern)**

* 在游戏模块中，使用 `router = APIRouter(prefix="/yourgame", tags=["YourGame"])`。
* 不要为游戏模块创建子 `FastAPI()` 应用。
* 导出的变量名必须是 `router`（供 `main.py` 的动态加载器使用）。

**2. 在主应用中注册 (Register in main app)**

* 在 `APPS_CONFIG` 中添加映射，例如：`"yourgame": "yourgame.app"`。
* 主应用应使用 `app.include_router(sub_router)`。
* 不要使用 `app.mount(..., sub_app)` 来挂载游戏 API。
* 如果需要静态文件，请在 `main.py` 中显式挂载到最终的带前缀的路径上。

**3. 数据库规范（仅限异步）**

* `database.py` 中的 API 均为异步函数；所有调用都必须使用 `await`。
* 不要在异步路由中使用阻塞式的 `sqlite3.connect(...)`。
* 新增的数据库辅助函数应使用 `async def` 定义，并保持返回的数据结构与现有的排行榜 API 结构一致。

**4. 生命周期与初始化 (Lifecycle and init)**

* 不要在游戏模块导入时（import time）调用 `init_db()`。
* 数据库的初始化已集中在应用的生命周期 (lifespan) 中处理：`await database.init_db()`。

**5. 导入规范 (Import rules)**

* 不要使用 `sys.path.insert(...)` 或 `sys.path.append(...)` 这种 Hack 写法。
* 使用标准的导入方式：`import database` 或 `from database import ...`。

**6. 前端 API 基础路径 (Frontend API base path)**

* 在前端代码中使用带有前缀的 API 基础路径，例如 `const API_BASE = '/yourgame/api'`。
* 保持页面路由和 API 前缀对齐（例如页面为 `/yourgame/`，API 为 `/yourgame/api/...`）。

**7. 合并前的快速检查 (Pre-merge quick checks)**

* 运行 `python -m compileall .` 能够顺利通过。
* 在主应用的 `/docs` (Swagger UI) 中可以正常看到新游戏的接口。
* 核心 API（如 `/api/status`、`/api/leaderboard` 以及写入接口）测试正常。
* 已经在首页和游戏列表中为新游戏添加了入口。