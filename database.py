import math
import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, List, Optional, Set

import aiosqlite

DB_NAME = "games.db"


# ---------------------------------------------------------------------------
# BoardGame 元数据模型 —— 宏加权算法基础
# ---------------------------------------------------------------------------

class BoardGame:
    """
    桌游元数据模型，用于 V3.1 双轨制对数优势模型。
    """

    def __init__(
        self,
        name: str,
        rating: float,
        complexity: float,
        min_players: int,
        max_players: int,
        default_duration: int,
        recommended_players: Optional[Set[int]] = None,
        game_type: str = "ffa",  # "ffa" | "faction" | "coop"
    ):
        self.name = name
        self.rating = rating
        self.complexity = complexity
        self.min_players = min_players
        self.max_players = max_players
        self.default_duration = default_duration
        self.recommended_players = recommended_players or set()
        self.game_type = game_type

    @property
    def w_static(self) -> float:
        """
        V3.1 静态硬核权重 W_static (Softplus 平滑非负化)。

        W* = [0.2×((R-5)/5) + 0.8×(C/5)²] × log₂(1 + T/15)
        W_static = τ × ln(1 + exp(W*/τ))    (τ=0.1)
        """
        alpha, beta, t0, tau = 0.2, 0.8, 15, 0.1
        r_trans = (self.rating - 5) / 5.0
        c_trans = (self.complexity / 5.0) ** 2
        w_star = (alpha * r_trans + beta * c_trans) * math.log2(
            1 + self.default_duration / t0
        )
        # Softplus 平滑: 防止 overflow，当 w_star/tau 很大时直接返回 w_star
        ratio = w_star / tau
        if ratio > 20:
            return w_star
        return tau * math.log(1 + math.exp(ratio))

    @property
    def weight(self) -> float:
        """向后兼容别名，等价于 w_static。"""
        return self.w_static

    @property
    def base_win_rate(self) -> float:
        """
        静态基准胜率 b_g。
        - Faction (阵营对抗): 0.5
        - Coop (纯合作): 0.5
        - FFA (纯竞争): 推荐人数倒数的期望
        """
        if self.game_type in ("faction", "coop"):
            return 0.5
        if self.recommended_players:
            return sum(1.0 / n for n in self.recommended_players) / len(
                self.recommended_players
            )
        avg_p = (self.min_players + self.max_players) / 2.0
        return 1.0 / avg_p


# ---------------------------------------------------------------------------
# 游戏元数据注册表 —— 统一维护各游戏的 rating / complexity / 人数 / 时长
# key 格式: "表名" 或 "表名:game_name"（用于 game_results 表中区分不同游戏）
# ---------------------------------------------------------------------------

GAME_REGISTRY: Dict[str, BoardGame] = {
    "game_results:Splendor": BoardGame(
        name="璀璨宝石",
        rating=7.4,
        complexity=2.31,
        min_players=2,
        max_players=4,
        default_duration=30,
        recommended_players={3},
        game_type="ffa",
    ),
    "game_results:Avalon": BoardGame(
        name="阿瓦隆",
        rating=7.4,
        complexity=2.12,
        min_players=5,
        max_players=12,
        default_duration=30,
        recommended_players={7, 8},
        game_type="faction",
    ),
    "lasvegas_leaderboard": BoardGame(
        name="拉斯维加斯",
        rating=7.5,
        complexity=1.42,
        min_players=2,
        max_players=6,
        default_duration=52.5,
        recommended_players={4, 5},
        game_type="ffa",
    ),
    "game_results:LoveLetters": BoardGame(
        name="情书",
        rating=7.4,
        complexity=1.30,
        min_players=2,
        max_players=8,
        default_duration=25,
        recommended_players={4, 5, 6},
        game_type="ffa",
    ),
    "game_results:ExplodingKittens": BoardGame(
        name="炸弹猫",
        rating=6.1,
        complexity=1.08,
        min_players=2,
        max_players=5,
        default_duration=15,
        recommended_players={4, 5},
        game_type="ffa",
    ),
    "cabo_game_results": BoardGame(
        name="卡波",
        rating=7.3,
        complexity=1.23,
        min_players=2,
        max_players=4,
        default_duration=45,
        recommended_players={3, 4},
        game_type="ffa",
    ),
    "flip7_game_results": BoardGame(
        name="7连翻",
        rating=7.2,
        complexity=1.03,
        min_players=3,
        max_players=18,
        default_duration=20,
        recommended_players={5, 6},
        game_type="ffa",
    ),
    "modernart_game_results": BoardGame(
        name="现代艺术",
        rating=7.5,
        complexity=2.28,
        min_players=3,
        max_players=5,
        default_duration=45,
        recommended_players={4, 5},
        game_type="ffa",
    ),
    "game_results:TheGang": BoardGame(
        name="纸牌帮",
        rating=7.6,
        complexity=1.60,
        min_players=3,
        max_players=6,
        default_duration=20,
        recommended_players={5},
        game_type="coop",
    ),
}



# ---------------------------------------------------------------------------
# V3.1 辅助数学函数 (logit / sigmoid / clamp)
# ---------------------------------------------------------------------------
EPS = 1e-6

def _clamp(x: float) -> float:
    return max(EPS, min(1 - EPS, x))

def _logit(x: float) -> float:
    x = _clamp(x)
    return math.log(x / (1 - x))

def _sigmoid(x: float) -> float:
    if x > 20:
        return 1.0
    if x < -20:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


@asynccontextmanager
async def _get_db() -> AsyncIterator[aiosqlite.Connection]:
    """统一的数据库连接获取入口。业务层应始终通过此函数获取连接。"""
    async with aiosqlite.connect(DB_NAME) as db:
        yield db


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS game_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_name TEXT NOT NULL,
                player_name TEXT NOT NULL,
                is_winner BOOLEAN NOT NULL,
                score INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS cabo_game_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                final_score INTEGER NOT NULL,
                is_winner BOOLEAN NOT NULL,
                round_count INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS lasvegas_leaderboard (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                game_amount INTEGER NOT NULL,
                bill_count INTEGER NOT NULL,
                is_winner BOOLEAN NOT NULL DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS flip7_game_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                final_score INTEGER NOT NULL,
                is_winner BOOLEAN NOT NULL,
                bust_count INTEGER NOT NULL DEFAULT 0,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS modernart_game_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id TEXT NOT NULL,
                player_name TEXT NOT NULL,
                final_money INTEGER NOT NULL,
                is_winner BOOLEAN NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Backward-compatible migration for old schemas.
        try:
            await db.execute(
                "ALTER TABLE flip7_game_results ADD COLUMN bust_count INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass

        try:
            await db.execute(
                "ALTER TABLE lasvegas_leaderboard ADD COLUMN is_winner BOOLEAN NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass

        await db.commit()

async def record_result(game_name: str, player_name: str, is_winner: bool, score: int = 0):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO game_results (game_name, player_name, is_winner, score)
            VALUES (?, ?, ?, ?)
            """,
            (game_name, player_name, is_winner, score),
        )
        await db.commit()

async def record_cabo_game(game_id: str, players_data: List[Dict]):
    """
    Record a completed Cabo game.
    players_data: [{"name": str, "final_score": int, "is_winner": bool, "round_count": int}, ...]
    """
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executemany(
            """
            INSERT INTO cabo_game_results (game_id, player_name, final_score, is_winner, round_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (game_id, p["name"], p["final_score"], p["is_winner"], p["round_count"])
                for p in players_data
            ],
        )
        await db.commit()

async def _fetch_scored_leaderboard(
    table_name: str,
    score_column: str,
    score_key: str,
    order_clause: str,
    registry_key: str = "",
    extra_agg_select: str = "",
    extra_row_parser=None,
) -> List[Dict]:
    """
    Shared leaderboard query for games with (game_id, player_name, is_winner, score-like field).
    V3.1 P_ladder: logit-space interpolation with reliability lock.
    """
    LAMBDA = 2.0
    K = 5  # 出勤常数
    K_PROVISIONAL = 3  # 定级阈值
    bg_obj = GAME_REGISTRY.get(registry_key)
    b_g = bg_obj.base_win_rate if bg_obj else 0.25

    async with aiosqlite.connect(DB_NAME) as db:
        db.row_factory = aiosqlite.Row
        extra_sql = f", {extra_agg_select}" if extra_agg_select else ""
        query = f"""
            SELECT player_name,
                   COUNT(DISTINCT game_id) as total_games,
                   SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as wins,
                   ROUND(AVG({score_column}), 1) as avg_value
                   {extra_sql}
            FROM {table_name}
            GROUP BY player_name
            ORDER BY {order_clause}
        """
        cursor = await db.execute(query)
        rows = await cursor.fetchall()

        ranked = []   # n_g >= K_PROVISIONAL  (正式天梯)
        provisional = []  # n_g < K_PROVISIONAL (定级试玩区)

        for row in rows:
            n_g = row["total_games"]
            w_g = row["wins"]
            # 1. Bayesian smoothed win rate (表现胜率)
            hat_p_g = (w_g + LAMBDA * b_g) / (n_g + LAMBDA) if n_g > 0 else b_g
            smoothed_pct = round(hat_p_g * 100, 1)
            # 2. Reliability lock (出勤锁)
            w_N = n_g / (n_g + K) if n_g > 0 else 0.0
            # 3. P_ladder via logit interpolation
            logit_blend = (1 - w_N) * _logit(b_g) + w_N * _logit(hat_p_g)
            p_ladder = _sigmoid(logit_blend)
            ladder_pct = round(p_ladder * 100, 1)
            # 4. Three-tier mastery
            if n_g < K_PROVISIONAL:
                mastery = "provisional"
            elif n_g < K:
                mastery = "rookie"
            else:
                mastery = "expert"

            item = {
                "name": row["player_name"],
                "total_games": n_g,
                "wins": w_g,
                "win_rate": ladder_pct,         # P_ladder (排名主键)
                "smoothed_rate": smoothed_pct,  # hat_p_g  (表现胜率)
                "mastery": mastery,
                score_key: row["avg_value"],
            }
            if extra_row_parser:
                item.update(extra_row_parser(row))

            if mastery == "provisional":
                provisional.append(item)
            else:
                ranked.append(item)

        # Sort ranked by P_ladder desc, then provisional by P_ladder desc
        ranked.sort(key=lambda x: -x["win_rate"])
        provisional.sort(key=lambda x: -x["win_rate"])
        stats = ranked + provisional

        cursor = await db.execute(
            f"""
            SELECT player_name, {score_column}
            FROM {table_name}
            WHERE game_id = (
                SELECT game_id FROM {table_name} ORDER BY timestamp DESC LIMIT 1
            )
            """
        )
        last_scores = {row[0]: row[1] for row in await cursor.fetchall()}
        last_key = "last_money" if score_key == "avg_money" else "last_score"
        for item in stats:
            item[last_key] = last_scores.get(item["name"])
        return stats


async def get_cabo_leaderboard() -> List[Dict]:
    """
    Returns Cabo leaderboard sorted by average score (lower is better).
    Includes last game score for each player.
    """
    return await _fetch_scored_leaderboard(
        table_name="cabo_game_results",
        score_column="final_score",
        score_key="avg_score",
        order_clause="avg_value ASC",
        registry_key="cabo_game_results",
    )

async def get_leaderboard() -> Dict[str, List[Dict]]:
    """
    Returns stats per game (Avalon).
    V3.1 P_ladder: logit-space interpolation with reliability lock.
    """
    LAMBDA = 2.0
    K = 5
    K_PROVISIONAL = 3
    bg_obj = GAME_REGISTRY.get("game_results:Avalon")
    b_g = bg_obj.base_win_rate if bg_obj else 0.5

    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
            SELECT player_name,
                   COUNT(*) as total_games,
                   SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as wins,
                   AVG(score) as avg_score
            FROM game_results
            WHERE game_name = 'Avalon'
            GROUP BY player_name
            ORDER BY wins DESC, total_games ASC
            """
        )
        rows = await cursor.fetchall()

    ranked = []
    provisional = []
    for row in rows:
        p_name, n_g, w_g, avg = row
        hat_p_g = (w_g + LAMBDA * b_g) / (n_g + LAMBDA) if n_g > 0 else b_g
        smoothed_pct = round(hat_p_g * 100, 1)
        w_N = n_g / (n_g + K) if n_g > 0 else 0.0
        logit_blend = (1 - w_N) * _logit(b_g) + w_N * _logit(hat_p_g)
        p_ladder = _sigmoid(logit_blend)
        ladder_pct = round(p_ladder * 100, 1)
        if n_g < K_PROVISIONAL:
            mastery = "provisional"
        elif n_g < K:
            mastery = "rookie"
        else:
            mastery = "expert"
        entry = {
            "name": p_name,
            "wins": w_g,
            "total": n_g,
            "win_rate": ladder_pct,
            "smoothed_rate": smoothed_pct,
            "mastery": mastery,
            "avg_score": round(avg, 1) if avg else 0,
        }
        if mastery == "provisional":
            provisional.append(entry)
        else:
            ranked.append(entry)
    ranked.sort(key=lambda x: -x["win_rate"])
    provisional.sort(key=lambda x: -x["win_rate"])
    return {"Avalon": ranked + provisional}


async def get_global_leaderboard() -> List[Dict]:
    """
    V3.1 双轨制对数优势模型排行榜。

    PvP (FFA + Faction):
      1. 贝叶斯平滑胜率 p̂_g = (w_g + λ·b_g) / (n_g + λ)
      2. 对数净优势 A_g = logit(p̂_g) − logit(b_g)
      3. 样本可靠性锁 w_N = n_g / (n_g + k)  (k=5)
      4. 动态权重 ω_g = W_static × w_N
      5. 总对数优势 A_total = Σ(ω_g × A_g) / Σ(ω_g)
      6. 标准参考胜率 P_final = sigmoid(logit(0.25) + A_total)

    PvE (Coop):
      1. 贝叶斯平滑通关率 p̂_g = (w_g + 2·0.5) / (n_g + 2)
      2. 可靠性锁 w_N = n_g / (n_g + 10)
      3. 动态权重 ω_g = W_static × w_N
      4. 综合通关率 P_final = Σ(ω_g × p̂_g) / Σ(ω_g)
    """

    # ── 辅助数学函数（使用模块级 _clamp/_logit/_sigmoid）───────

    # ── 数据查询 ─────────────────────────────────────────────
    queries = [
        ("game_results:Avalon",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM game_results WHERE game_name = 'Avalon'"),
        ("game_results:LoveLetters",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM game_results WHERE game_name = 'LoveLetters'"),
        ("cabo_game_results",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM cabo_game_results"),
        ("flip7_game_results",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM flip7_game_results"),
        ("modernart_game_results",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM modernart_game_results"),
        ("lasvegas_leaderboard",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM lasvegas_leaderboard"),
        ("game_results:Splendor",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM game_results WHERE game_name = 'Splendor'"),
        ("game_results:ExplodingKittens",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM game_results WHERE game_name = 'ExplodingKittens'"),
        ("game_results:TheGang",
         "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END "
         "FROM game_results WHERE game_name = 'TheGang'"),
    ]

    # player_name → { registry_key → {"w_g": int, "n_g": int} }
    per_game: Dict[str, Dict[str, Dict[str, int]]] = {}
    # 同时保留总局数 / 总胜场用于展示
    totals: Dict[str, Dict[str, int]] = {}

    async with aiosqlite.connect(DB_NAME) as db:
        for reg_key, sql in queries:
            try:
                cursor = await db.execute(sql)
                rows = await cursor.fetchall()
            except sqlite3.OperationalError:
                continue
            for p_name, games, wins in rows:
                per_game.setdefault(p_name, {}).setdefault(
                    reg_key, {"w_g": 0, "n_g": 0}
                )
                per_game[p_name][reg_key]["w_g"] += wins
                per_game[p_name][reg_key]["n_g"] += games
                totals.setdefault(p_name, {"total_games": 0, "total_wins": 0})
                totals[p_name]["total_games"] += games
                totals[p_name]["total_wins"] += wins

    # ── 算法常量 ─────────────────────────────────────────────
    LAMBDA = 2.0        # 贝叶斯先验强度
    K_PVP = 5           # PvP 出勤常数
    K_PVE = 10          # PvE 出勤常数
    REF_BASE = 0.25     # 标准 4 人局基准

    result = []
    for p_name, game_map in per_game.items():
        # ── PvP 累计 ─────────────────────────────────────
        pvp_sum_omega_A = 0.0   # Σ(ω_g × A_g)
        pvp_sum_omega = 0.0     # Σ(ω_g)

        # ── PvE 累计 ─────────────────────────────────────
        pve_sum_omega_p = 0.0   # Σ(ω_g × p̂_g)
        pve_sum_omega = 0.0     # Σ(ω_g)

        for reg_key, counts in game_map.items():
            bg = GAME_REGISTRY.get(reg_key)
            if bg is None:
                continue

            w_g = counts["w_g"]     # 胜场数
            n_g = counts["n_g"]     # 总局数
            if n_g <= 0:
                continue

            W_static = bg.w_static
            b_g = bg.base_win_rate

            if bg.game_type in ("ffa", "faction"):
                # ── PvP 分支 ──────────────────────────
                hat_p_g = _clamp((w_g + LAMBDA * b_g) / (n_g + LAMBDA))
                A_g = _logit(hat_p_g) - _logit(b_g)
                w_N = n_g / (n_g + K_PVP)
                omega_g = W_static * w_N
                pvp_sum_omega_A += omega_g * A_g
                pvp_sum_omega += omega_g
            else:
                # ── PvE 分支 (coop) ───────────────────
                hat_p_g = _clamp((w_g + LAMBDA * 0.5) / (n_g + LAMBDA))
                w_N = n_g / (n_g + K_PVE)
                omega_g = W_static * w_N
                pve_sum_omega_p += omega_g * hat_p_g
                pve_sum_omega += omega_g

        # ── 汇总指标 ─────────────────────────────────────
        if pvp_sum_omega > 0:
            A_total = pvp_sum_omega_A / pvp_sum_omega
            P_final = _sigmoid(_logit(REF_BASE) + A_total)
            pvp_rate = round(P_final * 100, 1)
        else:
            A_total = 0.0
            pvp_rate = 0.0

        pve_rate = None
        if pve_sum_omega > 0:
            pve_rate = round(pve_sum_omega_p / pve_sum_omega * 100, 1)

        t = totals.get(p_name, {"total_games": 0, "total_wins": 0})
        result.append({
            "name": p_name,
            "total_games": t["total_games"],
            "total_wins": t["total_wins"],
            "weighted_win_rate": pvp_rate,          # PvP 综合胜率 (%)
            "pvp_advantage": round(A_total, 3),     # PvP 隐藏优势分
            "pve_win_rate": pve_rate,                # PvE 通关率 (%)
            "pvp_data_strength": round(pvp_sum_omega, 2),
            "pve_data_strength": round(pve_sum_omega, 2),
        })

    result.sort(key=lambda x: (-x["weighted_win_rate"], -x["total_wins"]))
    return result


async def record_lasvegas_game(player_name: str, game_amount: int, bill_count: int, is_winner: bool = False):
    """Record a single player's Las Vegas game result."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO lasvegas_leaderboard (player_name, game_amount, bill_count, is_winner)
            VALUES (?, ?, ?, ?)
            """,
            (player_name, game_amount, bill_count, is_winner),
        )
        await db.commit()


async def get_lasvegas_leaderboard() -> List[Dict]:
    """Return Las Vegas leaderboard: cumulative total, latest game, total games played."""
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute(
            """
            SELECT player_name,
                   SUM(game_amount) as total_amount,
                   COUNT(*) as games_played
            FROM lasvegas_leaderboard
            GROUP BY player_name
            ORDER BY total_amount DESC
            """
        )
        cumulative_rows = await cursor.fetchall()
    cumulative = {}
    for row in cumulative_rows:
        games_played = row[2]
        cumulative[row[0]] = {
            "name": row[0],
            "total_amount": row[1],
            "games_played": games_played,
            "last_game_amount": 0,
            "last_game_bills": 0,
            "avg_amount": round(row[1] / games_played, 1) if games_played > 0 else 0,
        }

    # Get the latest game timestamp
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute("SELECT MAX(timestamp) FROM lasvegas_leaderboard")
        latest_ts_row = await cursor.fetchone()
    latest_ts = latest_ts_row[0] if latest_ts_row else None

    if latest_ts:
        async with aiosqlite.connect(DB_NAME) as db:
            cursor = await db.execute(
                """
                SELECT player_name, game_amount, bill_count
                FROM lasvegas_leaderboard
                WHERE timestamp = ?
                """,
                (latest_ts,),
            )
            last_rows = await cursor.fetchall()
        for row in last_rows:
            if row[0] in cumulative:
                cumulative[row[0]]["last_game_amount"] = row[1]
                cumulative[row[0]]["last_game_bills"] = row[2]

    # Sort by total_amount DESC
    result = sorted(cumulative.values(), key=lambda x: (-x["total_amount"], -x["games_played"]))
    return result

async def record_flip7_game(game_id: str, players_data: List[Dict]):
    """
    Record a completed Flip 7 game.
    players_data: [{"name": str, "final_score": int, "is_winner": bool, "bust_count": int}, ...]
    """
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executemany(
            """
            INSERT INTO flip7_game_results (game_id, player_name, final_score, is_winner, bust_count)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (game_id, p["name"], p["final_score"], p["is_winner"], p.get("bust_count", 0))
                for p in players_data
            ],
        )
        await db.commit()

async def get_flip7_leaderboard() -> List[Dict]:
    """
    Returns Flip 7 leaderboard sorted by wins (desc) and avg score (desc).
    Includes last game score for each player.
    """
    return await _fetch_scored_leaderboard(
        table_name="flip7_game_results",
        score_column="final_score",
        score_key="avg_score",
        order_clause="wins DESC, avg_value DESC",
        registry_key="flip7_game_results",
        extra_agg_select="SUM(bust_count) as total_busts",
        extra_row_parser=lambda row: {"total_busts": row["total_busts"] or 0},
    )

async def record_modernart_game(game_id: str, players_data: List[Dict]):
    """
    Record a completed Modern Art game.
    players_data: [{"name": str, "final_money": int, "is_winner": bool}, ...]
    """
    async with aiosqlite.connect(DB_NAME) as db:
        await db.executemany(
            """
            INSERT INTO modernart_game_results (game_id, player_name, final_money, is_winner)
            VALUES (?, ?, ?, ?)
            """,
            [(game_id, p["name"], p["final_money"], p["is_winner"]) for p in players_data],
        )
        await db.commit()

async def get_modernart_leaderboard() -> List[Dict]:
    """
    Returns Modern Art leaderboard sorted by wins (desc) and avg money (desc).
    """
    return await _fetch_scored_leaderboard(
        table_name="modernart_game_results",
        score_column="final_money",
        score_key="avg_money",
        order_clause="wins DESC, avg_value DESC",
        registry_key="modernart_game_results",
    )


async def get_simple_leaderboard(game_name: str) -> List[Dict]:
    """
    通用排行榜查询，用于只使用 game_results 表的简单游戏。
    V3.1 P_ladder: logit-space interpolation with reliability lock.
    """
    LAMBDA = 2.0
    K = 5
    K_PROVISIONAL = 3
    registry_key = f"game_results:{game_name}"
    bg_obj = GAME_REGISTRY.get(registry_key)
    b_g = bg_obj.base_win_rate if bg_obj else 0.25

    async with _get_db() as db:
        cursor = await db.execute(
            """
            SELECT player_name,
                   COUNT(*) as total_games,
                   SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as wins
            FROM game_results
            WHERE game_name = ?
            GROUP BY player_name
            ORDER BY wins DESC, total_games ASC
            """,
            (game_name,),
        )
        rows = await cursor.fetchall()

    ranked = []
    provisional = []
    for row in rows:
        p_name, n_g, w_g = row
        hat_p_g = (w_g + LAMBDA * b_g) / (n_g + LAMBDA) if n_g > 0 else b_g
        smoothed_pct = round(hat_p_g * 100, 1)
        w_N = n_g / (n_g + K) if n_g > 0 else 0.0
        logit_blend = (1 - w_N) * _logit(b_g) + w_N * _logit(hat_p_g)
        p_ladder = _sigmoid(logit_blend)
        ladder_pct = round(p_ladder * 100, 1)
        if n_g < K_PROVISIONAL:
            mastery = "provisional"
        elif n_g < K:
            mastery = "rookie"
        else:
            mastery = "expert"
        entry = {
            "name": p_name,
            "wins": w_g,
            "total": n_g,
            "win_rate": ladder_pct,
            "smoothed_rate": smoothed_pct,
            "mastery": mastery,
        }
        if mastery == "provisional":
            provisional.append(entry)
        else:
            ranked.append(entry)
    ranked.sort(key=lambda x: -x["win_rate"])
    provisional.sort(key=lambda x: -x["win_rate"])
    return ranked + provisional
