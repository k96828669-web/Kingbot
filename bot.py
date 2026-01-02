from flask import Flask, send_file, Response, request
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import os
from threading import Thread
import io
import asyncio

app = Flask(__name__)

# Bot configuration
BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
PORT = int(os.environ.get("PORT", 10000))

# In-memory storage
file_storage = {}

@app.route('/')
def home():
    return "✅ Bot is running! Send files to your Telegram bot."

@app.route('/stream/<file_id>')
def stream_file(file_id):
    """Stream file directly"""
    if file_id not in file_storage:
        return "❌ File not found or expired", 404
    
    file_data = file_storage[file_id]
    return send_file(
        io.BytesIO(file_data['content']),
        mimetype=file_data['mime_type'],
        as_attachment=False,
        download_name=file_data['filename']
    )

@app.route('/webhook', methods=['POST'])
def webhook():
    """Handle Telegram webhook"""
    return "OK", 200

# Telegram Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *File to Stream Link Bot*\n\n"
        "📤 Mujhe koi bhi file bhejo:\n"
        "• Videos 🎥\n"
        "• Audio 🎵\n"
        "• Documents 📄\n\n"
        "Main tumhe streamable link de dunga jo kisi bhi website par kaam karega! 🚀",
        parse_mode='Markdown'
    )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all types of files"""
    message = update.message
    file = None
    filename = None
    mime_type = "application/octet-stream"
    
    # Check file type
    if message.document:
        file = message.document
        filename = file.file_name
        mime_type = file.mime_type or mime_type
    elif message.video:
        file = message.video
        filename = f"video_{file.file_id}.mp4"
        mime_type = file.mime_type or "video/mp4"
    elif message.audio:
        file = message.audio
        filename = file.file_name or f"audio_{file.file_id}.mp3"
        mime_type = file.mime_type or "audio/mpeg"
    elif message.voice:
        file = message.voice
        filename = f"voice_{file.file_id}.ogg"
        mime_type = "audio/ogg"
    
    if not file:
        await message.reply_text("❌ Please send a valid file!")
        return
    
    # Check file size (50MB limit for free tier)
    file_size_mb = file.file_size / (1024 * 1024) if file.file_size else 0
    if file_size_mb > 50:
        await message.reply_text(f"❌ File too large ({file_size_mb:.1f}MB). Maximum 50MB allowed on free tier.")
        return
    
    # Send processing message
    status_msg = await message.reply_text("⏳ Processing your file...")
    
    try:
        # Download file
        telegram_file = await context.bot.get_file(file.file_id)
        file_bytes = await telegram_file.download_as_bytearray()
        
        # Store file in memory
        file_id = file.file_id
        file_storage[file_id] = {
            'content': bytes(file_bytes),
            'filename': filename,
            'mime_type': mime_type
        }
        
        # Get app URL from environment
        app_url = os.environ.get("RENDER_EXTERNAL_URL", f"http://localhost:{PORT}")
        stream_link = f"{app_url}/stream/{file_id}"
        
        # Create embed code
        embed_code = ""
        if mime_type.startswith('video/'):
            embed_code = f'\n\n📺 *Embed Code (HTML):*\n```html\n<video controls width="100%">\n  <source src="{stream_link}" type="{mime_type}">\n</video>\n```'
        elif mime_type.startswith('audio/'):
            embed_code = f'\n\n🎵 *Embed Code (HTML):*\n```html\n<audio controls>\n  <source src="{stream_link}" type="{mime_type}">\n</audio>\n```'
        
        await status_msg.edit_text(
            f"✅ *File Ready!*\n\n"
            f"📄 *File:* `{filename}`\n"
            f"📦 *Size:* {file_size_mb:.2f}MB\n"
            f"🔗 *Stream Link:*\n`{stream_link}`\n"
            f"{embed_code}\n\n"
            f"💡 *Ye link kisi bhi website par use ho sakta hai!*\n"
            f"⚠️ *Note:* Server restart hone par file delete ho jayegi.",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

def run_flask():
    """Run Flask server"""
    app.run(host='0.0.0.0', port=PORT, threaded=True)

async def setup_webhook(application: Application):
    """Setup webhook"""
    app_url = os.environ.get("RENDER_EXTERNAL_URL")
    if app_url:
        webhook_url = f"{app_url}/webhook"
        await application.bot.set_webhook(url=webhook_url)
        print(f"✅ Webhook set: {webhook_url}")
    else:
        print("⚠️ RENDER_EXTERNAL_URL not set, using polling mode")

def main():
    print("🚀 Starting bot...")
    
    # Start Flask in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print(f"✅ Flask server started on port {PORT}")
    
    # Create bot application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.VOICE, 
        handle_file
    ))
    
    # Setup webhook and start
    app_url = os.environ.get("RENDER_EXTERNAL_URL")
    if app_url:
        # Webhook mode
        asyncio.get_event_loop().run_until_complete(setup_webhook(application))
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path="/webhook",
            webhook_url=f"{app_url}/webhook"
        )
    else:
        # Polling mode (for local testing)
        print("⚠️ Running in polling mode (local testing)")
        application.run_polling()

if __name__ == '__main__':
    main()