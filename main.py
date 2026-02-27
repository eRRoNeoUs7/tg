from flask import Flask, jsonify, request
import praw
import os
from libsql_client import create_client

app = Flask(__name__)

# Yapılandırma
API_KEY = os.getenv("INTERNAL_API_KEY", "varsayilan_sifre") # cron-job.org'da kullanacağız
TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

# Reddit ve Turso Bağlantıları
def get_reddit():
    return praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent="web:reddit-fetcher:v1.0"
    )

def sync_data():
    client = create_client(url=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    reddit = get_reddit()
    
    # Tabloyu hazırla
    client.execute("CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, title TEXT, subreddit TEXT, created_at REAL)")
    
    subreddits = ["python", "datascience", "technology"]
    count = 0
    
    for sub_name in subreddits:
        for submission in reddit.subreddit(sub_name).new(limit=5):
            try:
                client.execute(
                    "INSERT INTO posts (id, title, subreddit, created_at) VALUES (?, ?, ?, ?)",
                    (submission.id, submission.title, sub_name, submission.created_utc)
                )
                count += 1
            except:
                continue
    
    client.close()
    return count

@app.route('/')
def home():
    return "Reddit Fetcher is Running!", 200

@app.route('/trigger-sync')
def trigger():
    # Basit güvenlik kontrolü
    key = request.args.get('key')
    if key != API_KEY:
        return jsonify({"error": "Yetkisiz erişim"}), 403
    
    try:
        new_posts = sync_data()
        return jsonify({"status": "success", "added": new_posts}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    # Render portu otomatik atar
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
