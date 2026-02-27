import telebot
import libsql_client
import os

# Şifreleri ve ID'leri sistemden (Koyeb'den) çekiyoruz
TOKEN = os.environ.get('BOT_TOKEN')
CHANNEL_ID = os.environ.get('CHANNEL_ID')
TURSO_URL = os.environ.get('TURSO_URL')
TURSO_TOKEN = os.environ.get('TURSO_TOKEN')

bot = telebot.TeleBot(TOKEN)

# Turso Veritabanına Bağlan
client = libsql_client.create_client_sync(url=TURSO_URL, auth_token=TURSO_TOKEN)

# Veritabanı Tablosu Kurulumu
client.execute('''
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, 
        file_id TEXT, 
        description TEXT
    )
''')

@bot.channel_post_handler(content_types=['video'])
def index_video(message):
    if str(message.chat.id) == CHANNEL_ID:
        file_id = message.video.file_id
        description = message.caption.lower() if message.caption else "isimsiz_video"
        
        client.execute(
            "INSERT INTO videos (file_id, description) VALUES (?, ?)", 
            [file_id, description]
        )

@bot.message_handler(func=lambda message: True)
def search_video(message):
    keyword = message.text.lower()
    
    result = client.execute(
        "SELECT file_id FROM videos WHERE description LIKE ?", 
        ['%' + keyword + '%']
    )

    if result.rows:
        bot.reply_to(message, f"{len(result.rows)} adet video bulundu. Gönderiliyor...")
        for row in result.rows:
            bot.send_video(message.chat.id, row[0])
    else:
        bot.reply_to(message, "Üzgünüm, bu aramayla eşleşen bir video bulamadım.")

print("Bot çalışıyor ve Turso'ya bağlandı...")
bot.polling(non_stop=True)
