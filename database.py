import sqlite3

class Database:
    def __init__(self, db_path: str = "outreach.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                platform TEXT NOT NULL,
                title TEXT NOT NULL,
                clicks INTEGER DEFAULT 0,
                conversions INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                github_url TEXT NOT NULL UNIQUE,
                repo TEXT NOT NULL,
                event_type TEXT NOT NULL,
                context_summary TEXT,
                reply_text TEXT NOT NULL,
                ai_provider TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.commit()
        conn.close()

    def add_post(self, url: str, platform: str, title: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "INSERT INTO posts (url, platform, title) VALUES (?, ?, ?)",
            (url, platform, title)
        )
        
        post_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return post_id
    
    def update_metrics(self, post_id: int, clicks: int = None, conversions: int = None):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if clicks is not None:
            cursor.execute("UPDATE posts SET clicks = ? WHERE id = ?", (clicks, post_id))
        
        if conversions is not None:
            cursor.execute("UPDATE posts SET conversions = ? WHERE id = ?", (conversions, post_id))
        
        conn.commit()
        conn.close()
    
    def get_recent_posts(self, limit: int = 10):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                id, url, platform, title, clicks, conversions, created_at,
                CASE 
                    WHEN clicks > 0 THEN (conversions * 100.0 / clicks)
                    ELSE NULL
                END as ctr
            FROM posts
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        
        posts = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return posts
    
    def get_posts_by_date_range(self, days: int):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT
                id, url, platform, title, clicks, conversions, created_at,
                CASE
                    WHEN clicks > 0 THEN (conversions * 100.0 / clicks)
                    ELSE 0
                END as ctr
            FROM posts
            WHERE created_at >= datetime('now', '-' || ? || ' days')
            ORDER BY created_at DESC
        """, (days,))

        posts = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return posts

    # --- Reply tracking methods ---

    def add_reply(self, github_url: str, repo: str, event_type: str,
                  context_summary: str, reply_text: str, ai_provider: str) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """INSERT INTO replies
               (github_url, repo, event_type, context_summary, reply_text, ai_provider)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (github_url, repo, event_type, context_summary, reply_text, ai_provider),
        )

        reply_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return reply_id

    def has_replied(self, github_url: str) -> bool:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM replies WHERE github_url = ?", (github_url,))
        exists = cursor.fetchone() is not None
        conn.close()
        return exists

    def get_recent_replies(self, limit: int = 20):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, github_url, repo, event_type, context_summary,
                   reply_text, ai_provider, created_at
            FROM replies
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))

        replies = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return replies

    def get_reply_stats(self, days: int = 7):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT repo) as repos
            FROM replies
            WHERE created_at >= datetime('now', '-' || ? || ' days')
        """, (days,))
        totals = dict(cursor.fetchone())

        cursor.execute("""
            SELECT event_type, COUNT(*) as count
            FROM replies
            WHERE created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY event_type
        """, (days,))
        by_type = [dict(row) for row in cursor.fetchall()]

        cursor.execute("""
            SELECT repo, COUNT(*) as count
            FROM replies
            WHERE created_at >= datetime('now', '-' || ? || ' days')
            GROUP BY repo ORDER BY count DESC LIMIT 10
        """, (days,))
        by_repo = [dict(row) for row in cursor.fetchall()]

        conn.close()
        return {
            "total": totals["total"],
            "repos": totals["repos"],
            "by_type": by_type,
            "by_repo": by_repo,
        }
