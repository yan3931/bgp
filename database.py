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
    桌游元数据模型，用于宏加权胜率计算。
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
    ):
        self.name = name
        self.rating = rating
        self.complexity = complexity
        self.min_players = min_players
        self.max_players = max_players
        self.default_duration = default_duration
        self.recommended_players = recommended_players or set()

    @property
    def p_rep(self) -> float:
        """
        表征理论人数 (Representative Player Count)。
        优先使用推荐人数的平均值；否则使用人数区间中位数。
        """
        if self.recommended_players:
            return sum(self.recommended_players) / len(self.recommended_players)
        return (self.min_players + self.max_players) / 2.0

    @property
    def weight(self) -> float:
        """
        游戏权重 W_i，用于宏加权胜率公式:
            P_total = Σ(W_i × S_i) / Σ(W_i)

        W = (α·R/10 + β·C/5) × log₂(1 + T/T₀) × max(1, log₂(P_rep))
        α=0.4, β=0.6, T₀=15
        """
        import math
        alpha, beta, t0 = 0.4, 0.6, 15
        quality = alpha * (self.rating / 10) + beta * (self.complexity / 5)
        effort = math.log2(1 + self.default_duration / t0)
        scale = max(1, math.log2(self.p_rep))
        return quality * effort * scale


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
    ),
    "game_results:Avalon": BoardGame(
        name="阿瓦隆",
        rating=7.5,
        complexity=1.74,
        min_players=5,
        max_players=12,
        default_duration=30,
        recommended_players={7, 8},
    ),
    "lasvegas_leaderboard": BoardGame(
        name="拉斯维加斯",
        rating=7.5,
        complexity=1.42,
        min_players=2,
        max_players=6,
        default_duration=52.5,
        recommended_players={4, 5},
    ),
    "game_results:LoveLetters": BoardGame(
        name="情书",
        rating=7.4,
        complexity=1.30,
        min_players=2,
        max_players=8,
        default_duration=25,
        recommended_players={4, 5, 6},
    ),
    "game_results:ExplodingKittens": BoardGame(
        name="炸弹猫",
        rating=6.1,
        complexity=1.08,
        min_players=2,
        max_players=5,
        default_duration=15,
        recommended_players={4, 5},
    ),
    "cabo_game_results": BoardGame(
        name="卡波",
        rating=7.3,
        complexity=1.23,
        min_players=2,
        max_players=4,
        default_duration=45,
        recommended_players={3, 4},
    ),
    "flip7_game_results": BoardGame(
        name="7连翻",
        rating=7.2,
        complexity=1.03,
        min_players=3,
        max_players=18,
        default_duration=20,
        recommended_players={5, 6},
    ),
    "modernart_game_results": BoardGame(
        name="现代艺术",
        rating=7.5,
        complexity=2.28,
        min_players=3,
        max_players=5,
        default_duration=45,
        recommended_players={4, 5},
    ),
    "game_results:TheGang": BoardGame(
        name="纸牌帮",
        rating=7.6,
        complexity=1.60,
        min_players=3,
        max_players=6,
        default_duration=20,
        recommended_players={5},
    ),
}


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
    extra_agg_select: str = "",
    extra_row_parser=None,
) -> List[Dict]:
    """
    Shared leaderboard query for games with (game_id, player_name, is_winner, score-like field).
    """
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

        stats = []
        for row in rows:
            total = row["total_games"]
            wins = row["wins"]
            item = {
                "name": row["player_name"],
                "total_games": total,
                "wins": wins,
                "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
                score_key: row["avg_value"],
            }
            if extra_row_parser:
                item.update(extra_row_parser(row))
            stats.append(item)

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
    )

async def get_leaderboard() -> Dict[str, List[Dict]]:
    """
    Returns stats per game:
    {
        "Avalon": [...],
        ...
    }
    """
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

    stats = []
    for row in rows:
        p_name, total, wins, avg = row
        stats.append(
            {
                "name": p_name,
                "wins": wins,
                "total": total,
                "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
                "avg_score": round(avg, 1) if avg else 0,
            }
        )
    return {"Avalon": stats}


async def get_global_leaderboard() -> List[Dict]:
    """
    宏加权胜率排行榜。

    公式:  P_total = Σ(W_i × S_i) / Σ(W_i)
      - S_i = 玩家在游戏 i 的胜率 (wins / games)
      - W_i = GAME_REGISTRY 中该游戏的 weight
    """

    # (registry_key, SQL) — 每条查询携带注册表 key 以便查找权重
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

    # player_name -> { registry_key -> {"games": int, "wins": int} }
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
                # 累计 per-game
                per_game.setdefault(p_name, {}).setdefault(
                    reg_key, {"games": 0, "wins": 0}
                )
                per_game[p_name][reg_key]["games"] += games
                per_game[p_name][reg_key]["wins"] += wins
                # 累计 totals
                totals.setdefault(p_name, {"total_games": 0, "total_wins": 0})
                totals[p_name]["total_games"] += games
                totals[p_name]["total_wins"] += wins

    result = []
    for p_name, game_map in per_game.items():
        sum_ws = 0.0   # Σ(W_i × S_i)
        sum_w = 0.0     # Σ(W_i)
        for reg_key, counts in game_map.items():
            bg = GAME_REGISTRY.get(reg_key)
            w = bg.weight if bg else 1.0
            s = counts["wins"] / counts["games"] if counts["games"] > 0 else 0.0
            sum_ws += w * s
            sum_w += w

        weighted_rate = (sum_ws / sum_w * 100) if sum_w > 0 else 0.0
        t = totals.get(p_name, {"total_games": 0, "total_wins": 0})
        result.append({
            "name": p_name,
            "total_games": t["total_games"],
            "total_wins": t["total_wins"],
            "weighted_win_rate": round(weighted_rate, 1),
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
        cumulative[row[0]] = {
            "name": row[0],
            "total_amount": row[1],
            "games_played": row[2],
            "last_game_amount": 0,
            "last_game_bills": 0,
            "avg_amount": round(row[1] / row[2], 1) if row[2] > 0 else 0
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
    )


async def get_simple_leaderboard(game_name: str) -> List[Dict]:
    """
    通用排行榜查询，用于只使用 game_results 表的简单游戏。
    返回按胜场降序排列的玩家统计列表。
    """
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

    stats = []
    for row in rows:
        p_name, total, wins = row
        stats.append({
            "name": p_name,
            "wins": wins,
            "total": total,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        })
    return stats
