from flask import Flask, jsonify, request
import praw
import os
import re
import time
from datetime import datetime, timedelta
import libsql

app = Flask(__name__)

# --- AYARLAR (Render Environment Variables'dan gelecek) ---
API_KEY = os.getenv("INTERNAL_API_KEY", "gizli_anahtar")
TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")
# Subredditleri virgülle ayırarak girin: "python,nosleep,writingprompts"
SUBREDDITS = os.getenv("REDDIT_CHANNELS", "python").split(",")
DAYS_BACK = int(os.getenv("DAYS_BACK", 1)) # Kaç günlük veri geriye dönük taransın?

# --- YARDIMCI FONKSİYONLAR (Mevcut kodunuzdan alındı) ---
def find_series_base(title):
    match = re.search(r'(.+?)([\s\-_]*(Part|Bölüm|Chapter|\#)[\s\-_]*\d+|\s+\d+)$', title.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip(), True
    return title, False

def get_db_conn():
    return libsql.connect(database=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)

def setup_db():
    conn = get_db_conn()
    cursor = conn.cursor()
    # Mevcut tablo yapınız (captured_content)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS captured_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            user TEXT,
            content TEXT,
            time REAL,
            link TEXT UNIQUE,
            channel TEXT,
            series_id INTEGER
        )
    """)
    conn.commit()
    conn.close()

# --- ANA MANTIK ---
def sync_reddit():
    conn = get_db_conn()
    cursor = conn.cursor()
    
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent="web:reddit-miner:v1.0"
    )

    new_posts_count = 0
    time_limit_utc = datetime.utcnow() - timedelta(days=DAYS_BACK)

    for channel_name in SUBREDDITS:
        channel_name = channel_name.strip()
        try:
            subreddit = reddit.subreddit(channel_name)
            for submission in subreddit.new(limit=50):
                post_time_utc = datetime.utcfromtimestamp(submission.created_utc)
                if post_time_utc < time_limit_utc:
                    break 

                link = "https://www.reddit.com" + submission.permalink
                user = submission.author.name if submission.author else "[deleted]"
                base_title, is_series = find_series_base(submission.title)
                
                series_id = None
                if is_series:
                    # Mevcut bir seri ID'si var mı kontrol et
                    cursor.execute(
                        "SELECT series_id FROM captured_content WHERE user = ? AND title LIKE ? AND series_id IS NOT NULL LIMIT 1",
                        (user, base_title + '%')
                    )
                    result = cursor.fetchone()
                    if result:
                        series_id = result[0]

                try:
                    cursor.execute("""
                        INSERT INTO captured_content (title, user, content, time, link, channel, series_id)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (submission.title, user, submission.selftext, submission.created_utc, link, channel_name, series_id))
                    new_posts_count += 1
                except:
                    # Link UNIQUE olduğu için mükerrer kayıtlar burada elenir
                    continue
            
            conn.commit()
        except Exception as e:
            print(f"Hata r/{channel_name}: {e}")

    conn.close()
    return new_posts_count

# --- ROUTES ---
@app.route('/')
def home():
    return "Reddit Miner Active", 200

@app.route('/trigger-sync')
def trigger():
    key = request.args.get('key')
    if key != API_KEY:
        return "Unauthorized", 403
    
    try:
        setup_db()
        added = sync_reddit()
        return jsonify({"status": "success", "new_posts": added}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
