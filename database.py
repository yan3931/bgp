import sqlite3
import datetime
from typing import List, Dict, Optional

DB_NAME = "games.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS game_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_name TEXT NOT NULL,
            player_name TEXT NOT NULL,
            is_winner BOOLEAN NOT NULL,
            score INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS cabo_game_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            player_name TEXT NOT NULL,
            final_score INTEGER NOT NULL,
            is_winner BOOLEAN NOT NULL,
            round_count INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS lasvegas_leaderboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_name TEXT NOT NULL,
            game_amount INTEGER NOT NULL,
            bill_count INTEGER NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS flip7_game_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            player_name TEXT NOT NULL,
            final_score INTEGER NOT NULL,
            is_winner BOOLEAN NOT NULL,
            bust_count INTEGER NOT NULL DEFAULT 0,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS modernart_game_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id TEXT NOT NULL,
            player_name TEXT NOT NULL,
            final_money INTEGER NOT NULL,
            is_winner BOOLEAN NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Try adding the column in case the table already exists from an older schema version
    try:
        c.execute("ALTER TABLE flip7_game_results ADD COLUMN bust_count INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass # Column might already exist
        
    conn.commit()
    conn.close()

def record_result(game_name: str, player_name: str, is_winner: bool, score: int = 0):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO game_results (game_name, player_name, is_winner, score)
        VALUES (?, ?, ?, ?)
    ''', (game_name, player_name, is_winner, score))
    conn.commit()
    conn.close()

def record_cabo_game(game_id: str, players_data: List[Dict]):
    """
    Record a completed Cabo game.
    players_data: [{"name": str, "final_score": int, "is_winner": bool, "round_count": int}, ...]
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for p in players_data:
        c.execute('''
            INSERT INTO cabo_game_results (game_id, player_name, final_score, is_winner, round_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (game_id, p["name"], p["final_score"], p["is_winner"], p["round_count"]))
    conn.commit()
    conn.close()

def get_cabo_leaderboard() -> List[Dict]:
    """
    Returns Cabo leaderboard sorted by average score (lower is better).
    Includes last game score for each player.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Get aggregate stats
    c.execute('''
        SELECT player_name,
               COUNT(DISTINCT game_id) as total_games,
               SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as wins,
               ROUND(AVG(final_score), 1) as avg_score
        FROM cabo_game_results
        GROUP BY player_name
        ORDER BY avg_score ASC
    ''')
    
    stats = []
    for row in c.fetchall():
        p_name, total, wins, avg = row
        stats.append({
            "name": p_name,
            "total_games": total,
            "wins": wins,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_score": avg
        })
    
    # Get last game scores
    c.execute('''
        SELECT player_name, final_score
        FROM cabo_game_results
        WHERE game_id = (
            SELECT game_id FROM cabo_game_results ORDER BY timestamp DESC LIMIT 1
        )
    ''')
    last_scores = {row[0]: row[1] for row in c.fetchall()}
    
    for s in stats:
        s["last_score"] = last_scores.get(s["name"], None)
    
    conn.close()
    return stats

def get_leaderboard() -> Dict[str, List[Dict]]:
    """
    Returns stats per game:
    {
        "Avalon": [...],
        ...
    }
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    leaderboard = {}
    
    c.execute('''
        SELECT player_name, 
               COUNT(*) as total_games,
               SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as wins,
               AVG(score) as avg_score
        FROM game_results
        WHERE game_name = 'Avalon'
        GROUP BY player_name
        ORDER BY wins DESC, total_games ASC
    ''')
    
    stats = []
    for row in c.fetchall():
        p_name, total, wins, avg = row
        stats.append({
            "name": p_name,
            "wins": wins,
            "total": total,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_score": round(avg, 1) if avg else 0
        })
    leaderboard['Avalon'] = stats
    
    conn.close()
    return leaderboard


def get_global_leaderboard() -> List[Dict]:
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    all_data = []
    
    try:
        c.execute('SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END FROM game_results')
        all_data.extend(c.fetchall())
    except sqlite3.OperationalError: pass
        
    try:
        c.execute('SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END FROM cabo_game_results')
        all_data.extend(c.fetchall())
    except sqlite3.OperationalError: pass
        
    try:
        c.execute('SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END FROM flip7_game_results')
        all_data.extend(c.fetchall())
    except sqlite3.OperationalError: pass
        
    try:
        c.execute('SELECT player_name, 1, CASE WHEN is_winner THEN 1 ELSE 0 END FROM modernart_game_results')
        all_data.extend(c.fetchall())
    except sqlite3.OperationalError: pass
        
    try:
        c.execute('SELECT player_name, 1, 0 FROM lasvegas_leaderboard')
        all_data.extend(c.fetchall())
    except sqlite3.OperationalError: pass
    
    conn.close()
    
    stats = {}
    for p_name, games, wins in all_data:
        if p_name not in stats:
            stats[p_name] = {"name": p_name, "total_games": 0, "total_wins": 0}
        stats[p_name]["total_games"] += games
        stats[p_name]["total_wins"] += wins
        
    result = list(stats.values())
    result.sort(key=lambda x: (-x["total_wins"], -x["total_games"]))
    return result


def record_lasvegas_game(player_name: str, game_amount: int, bill_count: int):
    """Record a single player's Las Vegas game result."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO lasvegas_leaderboard (player_name, game_amount, bill_count)
        VALUES (?, ?, ?)
    ''', (player_name, game_amount, bill_count))
    conn.commit()
    conn.close()


def get_lasvegas_leaderboard() -> List[Dict]:
    """Return Las Vegas leaderboard: cumulative total, latest game, total games played."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Get cumulative stats per player
    c.execute('''
        SELECT player_name,
               SUM(game_amount) as total_amount,
               COUNT(*) as games_played
        FROM lasvegas_leaderboard
        GROUP BY player_name
        ORDER BY total_amount DESC
    ''')
    cumulative = {}
    for row in c.fetchall():
        cumulative[row[0]] = {
            "name": row[0],
            "total_amount": row[1],
            "games_played": row[2],
            "last_game_amount": 0,
            "last_game_bills": 0,
            "avg_amount": round(row[1] / row[2], 1) if row[2] > 0 else 0
        }

    # Get the latest game timestamp
    c.execute('SELECT MAX(timestamp) FROM lasvegas_leaderboard')
    latest_ts_row = c.fetchone()
    latest_ts = latest_ts_row[0] if latest_ts_row else None

    if latest_ts:
        # Get each player's result from the latest game
        c.execute('''
            SELECT player_name, game_amount, bill_count
            FROM lasvegas_leaderboard
            WHERE timestamp = ?
        ''', (latest_ts,))
        for row in c.fetchall():
            if row[0] in cumulative:
                cumulative[row[0]]["last_game_amount"] = row[1]
                cumulative[row[0]]["last_game_bills"] = row[2]

    conn.close()

    # Sort by total_amount DESC
    result = sorted(cumulative.values(), key=lambda x: (-x["total_amount"], -x["games_played"]))
    return result

def record_flip7_game(game_id: str, players_data: List[Dict]):
    """
    Record a completed Flip 7 game.
    players_data: [{"name": str, "final_score": int, "is_winner": bool, "bust_count": int}, ...]
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for p in players_data:
        c.execute('''
            INSERT INTO flip7_game_results (game_id, player_name, final_score, is_winner, bust_count)
            VALUES (?, ?, ?, ?, ?)
        ''', (game_id, p["name"], p["final_score"], p["is_winner"], p.get("bust_count", 0)))
    conn.commit()
    conn.close()

def get_flip7_leaderboard() -> List[Dict]:
    """
    Returns Flip 7 leaderboard sorted by wins (desc) and avg score (desc).
    Includes last game score for each player.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Get aggregate stats
    c.execute('''
        SELECT player_name,
               COUNT(DISTINCT game_id) as total_games,
               SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as wins,
               ROUND(AVG(final_score), 1) as avg_score,
               SUM(bust_count) as total_busts
        FROM flip7_game_results
        GROUP BY player_name
        ORDER BY wins DESC, avg_score DESC
    ''')
    
    stats = []
    for row in c.fetchall():
        p_name, total, wins, avg, busts = row
        stats.append({
            "name": p_name,
            "total_games": total,
            "wins": wins,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_score": avg,
            "total_busts": busts or 0
        })
    
    # Get last game scores
    c.execute('''
        SELECT player_name, final_score
        FROM flip7_game_results
        WHERE game_id = (
            SELECT game_id FROM flip7_game_results ORDER BY timestamp DESC LIMIT 1
        )
    ''')
    last_scores = {row[0]: row[1] for row in c.fetchall()}
    
    for s in stats:
        s["last_score"] = last_scores.get(s["name"], None)
    
    conn.close()
    return stats

def record_modernart_game(game_id: str, players_data: List[Dict]):
    """
    Record a completed Modern Art game.
    players_data: [{"name": str, "final_money": int, "is_winner": bool}, ...]
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    for p in players_data:
        c.execute('''
            INSERT INTO modernart_game_results (game_id, player_name, final_money, is_winner)
            VALUES (?, ?, ?, ?)
        ''', (game_id, p["name"], p["final_money"], p["is_winner"]))
    conn.commit()
    conn.close()

def get_modernart_leaderboard() -> List[Dict]:
    """
    Returns Modern Art leaderboard sorted by wins (desc) and avg money (desc).
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Get aggregate stats
    c.execute('''
        SELECT player_name,
               COUNT(DISTINCT game_id) as total_games,
               SUM(CASE WHEN is_winner THEN 1 ELSE 0 END) as wins,
               ROUND(AVG(final_money), 1) as avg_money
        FROM modernart_game_results
        GROUP BY player_name
        ORDER BY wins DESC, avg_money DESC
    ''')
    
    stats = []
    for row in c.fetchall():
        p_name, total, wins, avg = row
        stats.append({
            "name": p_name,
            "total_games": total,
            "wins": wins,
            "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
            "avg_money": avg
        })
    
    # Get last game scores
    c.execute('''
        SELECT player_name, final_money
        FROM modernart_game_results
        WHERE game_id = (
            SELECT game_id FROM modernart_game_results ORDER BY timestamp DESC LIMIT 1
        )
    ''')
    last_scores = {row[0]: row[1] for row in c.fetchall()}
    
    for s in stats:
        s["last_money"] = last_scores.get(s["name"], None)
    
    conn.close()
    return stats
