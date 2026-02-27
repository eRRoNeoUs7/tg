import os
import re
import time
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
import praw
import libsql

app = Flask(__name__)

# --- YAPILANDIRMA (Render Environment Variables) ---
API_KEY = os.getenv("INTERNAL_API_KEY", "varsayilan_anahtar")
TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")
# Kanalları virgülle ayırarak girin: "nosleep,writingprompts,python"
REDDIT_CHANNELS = os.getenv("REDDIT_CHANNELS", "python").split(",")
DAYS_BACK = int(os.getenv("DAYS_BACK", 1))

# --- YARDIMCI FONKSİYONLAR ---
def find_series_base(title):
    """Orijinal kodundaki seri tespit mantığı"""
    match = re.search(r'(.+?)([\s\-_]*(Part|Bölüm|Chapter|\#)[\s\-_]*\d+|\s+\d+)$', title.strip(), re.IGNORECASE)
    if match:
        return match.group(1).strip(), True
    return title, False

def get_db_conn():
    return libsql.connect(database=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)

def setup_db():
    conn = get_db_conn()
    cursor = conn.cursor()
    # Link UNIQUE yapılarak mükerrer kayıt otomatik engellenir
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

# --- REDDIT VERİ ÇEKME MANTIĞI ---
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

    for channel_name in REDDIT_CHANNELS:
        channel_name = channel_name.strip()
        try:
            subreddit = reddit.subreddit(channel_name)
            # Render RAM limitini korumak için limit=25 idealdir
            for submission in subreddit.new(limit=25):
                post_time_utc = datetime.utcfromtimestamp(submission.created_utc)
                if post_time_utc < time_limit_utc:
                    break 

                link = "https://www.reddit.com" + submission.permalink
                user = submission.author.name if submission.author else "[deleted]"
                base_title, is_series = find_series_base(submission.title)
                
                series_id = None
                if is_series:
                    # Mevcut seri ID'sini Turso'dan sorgula
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
                    # Link UNIQUE olduğu için kayıt varsa buraya düşer, atlarız.
                    continue
            
            conn.commit()
        except Exception as e:
            print(f"Hata r/{channel_name}: {e}")

    conn.close()
    return new_posts_count

def run_background_sync():
    """Zaman aşımını önlemek için arka planda çalışan wrapper"""
    try:
        setup_db()
        added = sync_reddit()
        print(f"Bitti. {added} yeni kayıt eklendi.")
    except Exception as e:
        print(f"Arka plan hatası: {e}")

# --- FLASK ROTalari ---
@app.route('/')
def home():
    return "Reddit Miner is running...", 200

@app.route('/trigger-sync')
def trigger():
    # Güvenlik Kontrolü
    key = request.args.get('key')
    if key != API_KEY:
        return "Unauthorized", 403
    
    # İşlemi arka planda başlat ve hemen cevap dön (Timeout'u engeller)
    thread = threading.Thread(target=run_background_sync)
    thread.start()
    
    return jsonify({"status": "started", "message": "Sync process is running in background"}), 200

@app.route('/view-data')
def view_data():
    """Veritabanını kontrol etmek için basit bir endpoint"""
    conn = get_db_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, channel, series_id FROM captured_content ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    return jsonify(rows)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
