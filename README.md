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
<!-- Vue.js 渲染视图模板（包括空状态和列表项） -->
<div class="apple-list mb-xl">
    <!-- 空白状态 -->
    <div v-if="leaderboard.length === 0" class="text-center text-muted" style="padding: var(--space-xl);">
        <div class="empty-state">
            <span class="empty-icon">👻</span> <!-- 也可用 🏆, 🃏, 等贴合主题的表情 -->
            还没人玩过呢，快去开一局！
        </div>
    </div>
    
    <!-- 列表数据 -->
    <div v-else>
        <div v-for="(item, idx) in leaderboard" :key="item.name" class="apple-list-item" :style="item.mastery === 'provisional' ? 'opacity:0.65;' : ''">
            <!-- 1. 左侧名次/奖牌 -->
            <div class="rank-num"
                :class="idx === 0 ? 'rank-1' : (idx === 1 ? 'rank-2' : (idx === 2 ? 'rank-3' : 'rank-other'))">
                {{ idx === 0 ? '👑' : idx + 1 }}
            </div>

            <!-- 2. 中间玩家信息及战力概览 -->
            <div class="apple-list-item-content">
                <div class="apple-list-item-title">{{ item.name }} 
                    <span v-if="item.mastery === 'expert'" style="font-size:0.7rem;color:var(--apple-orange);font-weight:700;">👑专精</span>
                    <span v-else-if="item.mastery === 'rookie'" style="font-size:0.7rem;color:var(--apple-blue);font-weight:600;">🔰新手</span>
                    <span v-else style="font-size:0.7rem;color:var(--apple-gray);font-weight:600;">⏳定级中</span>
                </div>
                <div class="history-trail">{{ item.total_games }}局 · 战力{{ item.win_rate }}% · 胜率{{ item.smoothed_rate }}%</div>
            </div>

            <!-- 3. 右侧并排数值统计区 -->
            <div style="text-align: right; display: flex; align-items: center; gap: 16px;">
                <div style="text-align: right;">
                    <div class="history-trail" style="font-size: 0.7rem; margin-bottom: 2px;">业务指标A</div>
                    <div class="score-badge" style="font-size: 1.2rem; color: var(--apple-blue);">{{ item.avg_score }}</div>
                </div>
                <div style="text-align: right; width: 40px;">
                    <div class="history-trail" style="font-size: 0.7rem; margin-bottom: 2px;">指标B</div>
                    <div class="score-badge" style="font-size: 1.1rem; color: var(--apple-gray);">{{ item.last_score !== null ? item.last_score : '--' }}</div>
                </div>
            </div>
        </div>
    </div>
</div>
```

---

## 5. V3.1 双轨制对数优势模型 (Rating System)
本项目在战力排行上抛弃了粗暴的“胜率直排”或“净胜场排”，采用了一套借鉴 Elo 思想并专门针对“少样本、高开荒门槛”桌游定制的 **双轨制对数优势模型 (Double-track Logarithmic Advantage Model)**。

### 桌游战力统计算法（双轨制对数优势模型）

该算法旨在仅依赖“游戏静态元数据”与“玩家个人胜负频次”的前提下，过滤运气成分、惩罚小样本暴击，最终提炼出玩家真实的“硬核策略实力”。

#### 一、 算法输入定义

为了进行计算，算法需要两组基础数据：

**游戏静态元数据 (Game Metadata)**

* $R$: BGG 评分 (Rating，通常在 1~10 之间)
* $C$: BGG 复杂度 (Complexity / Weight，通常在 1~5 之间)
* $T$: 游戏标称时长 (Duration，单位：分钟)
* $S_{rep}$: 推荐人数集合 (例如 $\{4, 5\}$)
* $Type$: 游戏类型（分为 纯竞争 FFA、阵营对抗 Faction、纯合作 Coop）

**玩家单项游戏战绩 (Player Record)**

* $w_g$: 在该游戏中的胜场数 (Wins)
* $n_g$: 在该游戏中的总游玩局数 (Total Matches)

---

#### 二、 核心模块 1：静态硬核权重计算 ($W_{static}$)

**目的：** 确立游戏的“含金量”。高分、重度、长耗时的游戏将获得极高的权重，而轻度运气游戏权重极低。此权重对所有玩家固定不变。

**步骤 1：计算原始战力基数 ($W^*$)**
结合评分的线性偏移与复杂度的指数（平方）惩罚，并乘以边际递减的时长乘数（以 15 分钟为基准）：


$$W^* = \left[ 0.2 \times \left( \frac{R - 5}{5} \right) + 0.8 \times \left( \frac{C}{5} \right)^2 \right] \times \log_2\left(1 + \frac{T}{15}\right)$$

**步骤 2：Softplus 平滑非负化 ($W_{static}$)**
为了防止极低评分/复杂度的游戏算出负数权重导致逻辑崩塌，使用 Softplus 函数进行平滑托底（设平滑系数 $\tau = 0.1$）。当 $W^*$ 为负时，结果无限趋近于 0 但不为负；当 $W^*$ 较大时，结果几乎等于 $W^*$。


$$W_{static} = \tau \times \ln\left(1 + \exp\left(\frac{W^*}{\tau}\right)\right)$$

---

#### 三、 核心模块 2：PvP 竞技战力面板计算

**适用范围：** 纯竞争 (FFA) 与阵营对抗 (Faction) 游戏。
**目的：** 计算玩家在玩家对抗中的相对优势，并汇总为综合胜率。

**步骤 1：计算静态基准胜率 ($b_g$)**
消除不同游戏人数带来的天然胜率差异。为了避免平均倒数陷阱（Jensen 不等式误差），严格计算推荐人数倒数的期望。

* 如果是阵营对抗 (Faction)：$b_g = 0.5$
* 如果是纯竞争 (FFA)：$b_g = \frac{1}{|S_{rep}|} \sum_{n \in S_{rep}} \frac{1}{n}$
*(例如推荐人数为 $\{4, 5\}$，则 $b_g = \frac{1}{2}(\frac{1}{4} + \frac{1}{5}) = 0.225$)*

**步骤 2：贝叶斯平滑胜率 ($\hat{p}_g$)**
向基准胜率收缩，防止玩家只玩一局就获得 100% 或 0% 的极端胜率（设先验强度 $\lambda = 2.0$）。


$$\hat{p}_g = \frac{w_g + \lambda \times b_g}{n_g + \lambda}$$


*(注：计算后需在极值处做微小裁剪，如限制在 $[10^{-6}, 1 - 10^{-6}]$ 之间，防止后续对数计算溢出)*

**步骤 3：计算对数净优势 ($A_g$)**
利用 Logit 函数将胜率转化为“实力净值”。这使得超越 50% 基准和超越 20% 基准的难度得以在数学上等价比较。


$$\text{logit}(x) = \ln\left(\frac{x}{1 - x}\right)$$

$$A_g = \text{logit}(\hat{p}_g) - \text{logit}(b_g)$$


*(若 $A_g > 0$，说明玩家表现高于该游戏理论平均水平)*

**步骤 4：引入样本可靠性锁 ($w_N$)**
惩罚游玩次数过少的游戏，防止偶然的高权重高胜率对局引起总面板震荡（设 PvP 出勤常数 $k = 5$）。


$$w_N = \frac{n_g}{n_g + k}$$

**步骤 5：计算单款游戏的最终动态权重 ($\omega_g$)**


$$\omega_g = W_{static} \times w_N$$

**步骤 6：汇总总对数优势 ($A_{total}$)**
将玩家所有 PvP 游戏的优势值用动态权重进行加权平均，得出一个类似 ELO 隐藏分的绝对战力值。


$$A_{total} = \frac{\sum (\omega_g \times A_g)}{\sum \omega_g}$$

**步骤 7：映射为标准参考胜率 ($P_{final}$)**
将抽象的 $A_{total}$ 投射到一个“标准的 4 人高难策略局”（基准为 0.25）中，还原成人类直觉可读的百分比胜率（使用 Sigmoid 逆变换）。


$$P_{final} = \frac{1}{1 + \exp\left(-\left(\text{logit}(0.25) + A_{total}\right)\right)}$$

---

#### 四、 核心模块 3：PvE 合作通关面板计算

**适用范围：** 纯合作 (Coop) 游戏。
**目的：** 合作游戏的胜率受剧本难度和队友影响极大，无法定义绝对公平的竞技基准，因此从 PvP 中剥离，单独降维计算“平滑通关率”。

**步骤 1：贝叶斯平滑通关率 ($\hat{p}^{(pve)}_g$)**
向中立期望 50% 进行平滑（设 $\lambda = 2.0$）。


$$\hat{p}^{(pve)}_g = \frac{w_g + \lambda \times 0.5}{n_g + \lambda}$$

**步骤 2：应用更严格的可靠性锁 ($w_N$)**
因为合作游戏的随机性与“抱大腿”效应更强，使用更大的惩罚常数（设 PvE 出勤常数 $k = 10$）。


$$w_N = \frac{n_g}{n_g + 10}$$


最终动态权重依然为：


$$\omega_g = W_{static} \times w_N$$

**步骤 3：汇总综合通关率 ($P^{(pve)}_{final}$)**
直接对平滑后的通关率进行加权平均，不再进行复杂的对数优势转换。


$$P^{(pve)}_{final} = \frac{\sum (\omega_g \times \hat{p}^{(pve)}_g)}{\sum \omega_g}$$

---

#### 五、 算法最终输出结果

经过上述运算，系统最终会输出以下关键指标供前端展示：

* **PvP 综合战力胜率 ($P_{final}$)**：剔除水分与运气后的核心实力体现。
* **PvP 隐藏优势分 ($A_{total}$)**：不受百分比上限影响的绝对战力数值。
* **PvE 综合通关率 ($P^{(pve)}_{final}$)**：反映玩家参与团队游戏的整体成功率。
* **有效数据量度 ($\sum \omega_g$)**：用于判断当前面板数据是否充分。若该值过低（例如小于 2.0），系统可提示“数据样本不足，定级中”。

---

### 一、 核心设计目标与哲学

1. **剥离全局权重**：在单一游戏榜单中，所有人面对的重度、机制完全相同，因此废弃 $W_{static}$，只比较“该游戏内的相对统治力”。
2. **根除“小样本锁榜”毒瘤**：绝不使用纯胜率或平滑胜率直接排序，必须让“打得多且稳”的玩家压制“赢两把就跑”的欧皇。
3. **UI 认知降维**：将抽象的数学惩罚（排序分）反向映射回百分比胜率（天梯保守胜率），做到“底层硬核防刷，表层直观易懂”。

---

### 二、 算法输入定义

对于当前正在计算榜单的特定游戏 $g$，需拉取该游戏的基础元数据，以及所有参与过该游戏的玩家战绩。

**游戏静态基准 (Game Baseline)**

* $b_g$: 该游戏的静态基准胜率。
* 阵营对抗类：$b_g = 0.5$
* 纯竞争 (FFA) 类：$b_g = \frac{1}{|S_{rep}|} \sum_{n \in S_{rep}} \frac{1}{n}$ （推荐人数倒数的期望）



**玩家单作战绩 (Player Record)**

* $w_g$: 玩家在该游戏中的总胜场数。
* $n_g$: 玩家在该游戏中的总游玩局数。

---

### 三、 核心计算逻辑（四步走）

针对每一位玩家，按以下四个步骤计算其天梯指标：

#### 步骤 1：计算贝叶斯平滑表现胜率 ($\hat{p}_g$)

**目的**：消除 0 胜和全胜的极端百分比，向基准胜率靠拢。
**公式**：


$$\hat{p}_g = \frac{w_g + \lambda \times b_g}{n_g + \lambda}$$


*(注：$\lambda$ 为先验强度常数，推荐设为 2.0。计算后需使用 clamp 函数限制在微小极值区间，防止对数运算溢出。)*

#### 步骤 2：计算样本可靠性锁 / 出勤权重 ($w_N$)

**目的**：衡量系统对该玩家当前数据的“信任程度”。局数越少，信任度越接近 0；局数越多，信任度越接近 1。
**公式**：


$$w_N = \frac{n_g}{n_g + k}$$


*(注：$k$ 为该子榜单的局部出勤常数，推荐设为 3 到 5 之间。)*

#### 步骤 3：Logit 空间下的引力拔河（隐性排序分）

**目的**：在对数几率（Logit）空间中，让“游戏的客观基准”与“玩家的主观表现”根据可靠性锁进行加权拔河。
**公式**：


$$\text{Score} = (1 - w_N) \times \text{logit}(b_g) + w_N \times \text{logit}(\hat{p}_g)$$


*(注：$\text{logit}(x) = \ln(x / (1 - x))$。当局数极少时，分数被死死锚定在游戏的客观基准处；当局数足够多时，分数彻底倒向玩家的主观表现。)*

#### 步骤 4：生成天梯保守胜率 ($P_{ladder}$)

**目的**：将抽象的拔河得分映射回 [0, 1] 的概率空间，作为前端最终展示和天梯排序的**唯一主键**。
**公式**：


$$P_{ladder} = \text{sigmoid}(\text{Score})$$


*(注：$\text{sigmoid}(x) = 1 / (1 + \exp(-x))$。)*

---

### 四、 排行榜生成与 UI 展示规范

经过上述计算，每位玩家都会获得三个核心属性：$n_g$（局数）、$\hat{p}_g$（平滑胜率）和 $P_{ladder}$（天梯保守胜率）。
最后，通过以下规则生成输出列表：

#### 1. 榜单隔离规则（生态保护）

设定一个最小入榜局数阈值 $N_{min}$（例如 3 局）。

* **正式天梯区**：$n_g \ge N_{min}$ 的玩家。参与正式排名。
* **定级试玩区**：$n_g < N_{min}$ 的玩家。不参与排名，强制置于榜单底部，按局数或平滑胜率暗排， UI 灰化处理。

#### 2. 排序规则

在“正式天梯区”内，**严格按照 $P_{ladder}$ 从高到低降序排列**。若 $P_{ladder}$ 相同，则按总胜场数 $w_g$ 降序，再按总局数 $n_g$ 降序。

#### 3. 前端 UI 渲染字段分配

* **主排名分数（大字强调）**：渲染 $P_{ladder}$（例如展示为 **“天梯战力：45.2%”**）。向玩家传达“这是系统目前认可你的保守胜率”。
* **表现胜率（副文本展示）**：渲染 $\hat{p}_g$（例如展示为 **“平滑胜率：55.0%”**）。向玩家传达“这是你目前的纸面表现”。
* **熟练度标签（根据 $n_g$ 动态挂载）**：
* $n_g < 3$：⏳ 试玩 / 定级中
* $3 \le n_g < 10$：⚔️ 熟手 / 入榜
* $n_g \ge 10$：👑 专精

---

## 6. 常见注意事项与避坑指南 (Caveats)
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