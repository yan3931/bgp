import sqlite3
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, List

import aiosqlite

DB_NAME = "games.db"


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
    all_data = []
    async with aiosqlite.connect(DB_NAME) as db:
        for query in [
            "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END FROM game_results",
            "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END FROM cabo_game_results",
            "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END FROM flip7_game_results",
            "SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END FROM modernart_game_results",
            "SELECT player_name, 1, 0 FROM lasvegas_leaderboard",
        ]:
            try:
                cursor = await db.execute(query)
                all_data.extend(await cursor.fetchall())
            except sqlite3.OperationalError:
                pass

    stats = {}
    for p_name, games, wins in all_data:
        if p_name not in stats:
            stats[p_name] = {"name": p_name, "total_games": 0, "total_wins": 0}
        stats[p_name]["total_games"] += games
        stats[p_name]["total_wins"] += wins
        
    result = list(stats.values())
    result.sort(key=lambda x: (-x["total_wins"], -x["total_games"]))
    return result


async def record_lasvegas_game(player_name: str, game_amount: int, bill_count: int):
    """Record a single player's Las Vegas game result."""
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            """
            INSERT INTO lasvegas_leaderboard (player_name, game_amount, bill_count)
            VALUES (?, ?, ?)
            """,
            (player_name, game_amount, bill_count),
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
