from flask import Flask, jsonify, request
import praw
import os
import libsql # Yeni kütüphane

app = Flask(__name__)

API_KEY = os.getenv("INTERNAL_API_KEY", "varsayilan_sifre")
TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")

def sync_data():
    # Libsql (SQLite uyumlu) bağlantısı
    # Bu kütüphane event loop gerektirmez, Flask ile doğrudan çalışır
    conn = libsql.connect(database=TURSO_URL, auth_token=TURSO_AUTH_TOKEN)
    cursor = conn.cursor()
    
    # Reddit Bağlantısı
    reddit = praw.Reddit(
        client_id=os.getenv("REDDIT_CLIENT_ID"),
        client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
        user_agent="web:reddit-fetcher:v1.0"
    )

    # Tabloyu oluştur
    cursor.execute("CREATE TABLE IF NOT EXISTS posts (id TEXT PRIMARY KEY, title TEXT, subreddit TEXT, created_at REAL)")
    
    subreddits = ["Nsfw_Hikayeler"]
    count = 0
    
    for sub_name in subreddits:
        for submission in reddit.subreddit(sub_name).new(limit=25):
            try:
                cursor.execute(
                    "INSERT INTO posts (id, title, subreddit, created_at) VALUES (?, ?, ?, ?)",
                    (submission.id, submission.title, sub_name, submission.created_utc)
                )
                count += 1
            except:
                continue # Duplicate kayıtları atla
    
    conn.commit() # Değişiklikleri kaydet
    conn.close()
    return count

@app.route('/')
def home():
    return "Reddit Fetcher is Running!", 200

@app.route('/trigger-sync')
def trigger():
    key = request.args.get('key')
    if key != API_KEY:
        return jsonify({"error": "Yetkisiz erişim"}), 403
    
    try:
        new_posts = sync_data()
        return jsonify({"status": "success", "added": new_posts}), 200
    except Exception as e:
        # Hatanın ne olduğunu daha net görmek için:
        print(f"Hata Detayı: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
