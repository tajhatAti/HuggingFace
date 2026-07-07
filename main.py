import os
import asyncio
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import TelegramError, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from huggingface_hub import HfApi, HfFolder
import aiohttp

# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_REPO = os.environ.get("HF_REPO", "")
HF_USERNAME = os.environ.get("HF_USERNAME", "Madarauchihagmailcom") # তোমার HF ইউজারনেম
HF_TYPE = os.environ.get("HF_TYPE", "space")  # "space" or "model" or "dataset"
PORT = int(os.environ.get("PORT", 8080))

WORKSPACE_FILE = "hf_workspace.json"

# ============================================================
# HTTP HEALTH SERVER (For Render Keep-Alive)
# ============================================================
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    
    def log_message(self, *args):
        pass

def run_health_server():
    HTTPServer(('0.0.0.0', PORT), HealthHandler).serve_forever()

# ============================================================
# HUGGING FACE API
# ============================================================
api = HfApi(token=HF_TOKEN)

async def hf_list_repo_tree(repo_id, path="", recursive=False):
    try:
        items = api.list_repo_tree(
            repo_id=repo_id,
            repo_type=HF_TYPE,
            path=path,
            recursive=recursive
        )
        return list(items)
    except Exception as e:
        return None

async def hf_get_file_content(repo_id, path):
    try:
        url = f"https://huggingface.co/{repo_id}/resolve/main/{path}"
        if HF_TYPE == "space":
            url = f"https://huggingface.co/spaces/{repo_id}/resolve/main/{path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers={"Authorization": f"Bearer {HF_TOKEN}"}) as resp:
                if resp.status == 200:
                    return await resp.text()
        return None
    except Exception as e:
        return None

async def hf_upload_file(repo_id, path, content):
    try:
        api.upload_file(
            path_or_fileobj=content.encode("utf-8") if isinstance(content, str) else content,
            path_in_repo=path,
            repo_id=repo_id,
            repo_type=HF_TYPE,
            token=HF_TOKEN
        )
        return True
    except Exception as e:
        return False

async def hf_delete_file(repo_id, path):
    try:
        api.delete_file(
            path_in_repo=path,
            repo_id=repo_id,
            repo_type=HF_TYPE,
            token=HF_TOKEN
        )
        return True
    except Exception as e:
        return False

async def hf_create_repo(repo_id, private=False):
    try:
        api.create_repo(
            repo_id=repo_id,
            repo_type=HF_TYPE,
            private=private,
            token=HF_TOKEN
        )
        return True
    except Exception as e:
        return False

async def hf_get_repo_info(repo_id):
    try:
        info = api.repo_info(repo_id=repo_id, repo_type=HF_TYPE)
        return info
    except Exception as e:
        return None

# ============================================================
# PERSISTENCE
# ============================================================
def load_workspace():
    if os.path.exists(WORKSPACE_FILE):
        try:
            with open(WORKSPACE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_workspace(data):
    with open(WORKSPACE_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ============================================================
# CONVERSATION STATES
# ============================================================
CHOOSING, WRITING_CONTENT, REPO_NAME, REPO_PRIVACY = range(4)

# ============================================================
# HANDLERS
# ============================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return
    
    await update.message.reply_text(
        "🤖 **Hugging Face Repo Manager Bot**\n\n"
        "/info - Repository info\n"
        "/files - Browse files\n"
        "/write - Write/edit file\n"
        "/delete_file - Delete file\n"
        "/new_repo - Create new repo\n"
        "/help - Commands help",
        parse_mode="markdown"
    )

async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    msg = await update.message.reply_text("⏳ Fetching repository info...")
    info_data = await hf_get_repo_info(HF_REPO)
    
    if not info_data:
        await msg.edit_text("❌ Could not fetch repo info")
        return
    
    private = info_data.private if hasattr(info_data, 'private') else False
    created_at = str(info_data.created_at) if hasattr(info_data, 'created_at') else "Unknown"
    updated_at = str(info_data.last_modified) if hasattr(info_data, 'last_modified') else "Unknown"
    
    text = (
        f"📦 **{HF_REPO}**\n\n"
        f"🔒 Privacy: `{'Private' if private else 'Public'}`\n"
        f"📅 Created: `{created_at}`\n"
        f"⏱️ Updated: `{updated_at}`\n"
        f"🔗 [View on HF](https://huggingface.co/{HF_REPO})"
    )
    await msg.edit_text(text, parse_mode="markdown")

async def files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    msg = await update.message.reply_text("⏳ Loading files...")
    items = await hf_list_repo_tree(HF_REPO, path="")
    
    if items is None:
        await msg.edit_text("❌ Could not load files")
        return
    
    text = f"📂 **{HF_REPO}**\n\n"
    dirs = [item for item in items if item.type == "folder"]
    files_list = [item for item in items if item.type == "file"]
    
    if dirs:
        text += "**Directories:**\n"
        for d in dirs[:20]:
            text += f"📁 `{d.path}`\n"
    
    if files_list:
        text += "\n**Files:**\n"
        for f in files_list[:20]:
            text += f"📄 `{f.path}`\n"
    
    if len(dirs) > 20 or len(files_list) > 20:
        text += "\n_(More items not shown)_"
    
    await msg.edit_text(text, parse_mode="markdown")

async def write_file_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    await update.message.reply_text(
        "📝 Send file path (e.g. `app/main.py`):",
        parse_mode="markdown"
    )
    return CHOOSING

async def write_file_path(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file_path = update.message.text.strip()
    if not file_path:
        await update.message.reply_text("❌ Invalid path")
        return CHOOSING
    
    context.user_data['file_path'] = file_path
    await update.message.reply_text(
        f"✍️ Send content for `{file_path}`:",
        parse_mode="markdown"
    )
    return WRITING_CONTENT

async def write_file_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    content = update.message.text
    file_path = context.user_data.get('file_path')
    
    msg = await update.message.reply_text(f"⏳ Uploading `{file_path}`...", parse_mode="markdown")
    success = await hf_upload_file(HF_REPO, file_path, content)
    
    if success:
        await msg.edit_text(f"✅ File updated: `{file_path}`", parse_mode="markdown")
    else:
        await msg.edit_text(f"❌ Failed to upload file", parse_mode="markdown")
    return ConversationHandler.END

async def delete_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    args = update.message.text.split(' ', 1)
    if len(args) < 2:
        await update.message.reply_text("❌ Format: /delete_file [path]\nExample: `/delete_file test.py`", parse_mode="markdown")
        return
    
    file_path = args[1].strip()
    msg = await update.message.reply_text(f"⏳ Deleting `{file_path}`...", parse_mode="markdown")
    success = await hf_delete_file(HF_REPO, file_path)
    
    if success:
        await msg.edit_text(f"✅ File deleted: `{file_path}`", parse_mode="markdown")
    else:
        await msg.edit_text(f"❌ Could not delete file", parse_mode="markdown")

async def new_repo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    await update.message.reply_text(
        "📦 **Create New Repository**\n\nSend repo name (e.g. `my-awesome-space`):",
        parse_mode="markdown"
    )
    return REPO_NAME

async def new_repo_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    repo_name = update.message.text.strip()
    if not repo_name or len(repo_name) < 3:
        await update.message.reply_text("❌ Invalid repo name")
        return REPO_NAME
    
    context.user_data['repo_name'] = repo_name
    
    keyboard = [
        [InlineKeyboardButton("🌐 Public", callback_data="privacy:public"),
         InlineKeyboardButton("🔒 Private", callback_data="privacy:private")]
    ]
    
    await update.message.reply_text(
        f"🔒 Choose privacy for `{repo_name}`:",
        parse_mode="markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return REPO_PRIVACY

async def new_repo_privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    privacy = query.data.split(":")[1]
    is_private = privacy == "private"
    repo_name = context.user_data.get('repo_name')
    
    msg = await query.edit_message_text(
        f"⏳ Creating repo `{repo_name}` ({privacy})...",
        parse_mode="markdown"
    )
    
    full_repo_id = f"{HF_USERNAME}/{repo_name}"
    success = await hf_create_repo(full_repo_id, private=is_private)
    
    if success:
        await msg.edit_text(
            f"✅ Repository created!\n\n"
            f"📦 **{full_repo_id}**\n"
            f"🔗 [View on HF](https://huggingface.co/{HF_TYPE}s/{full_repo_id})",
            parse_mode="markdown"
        )
    else:
        await msg.edit_text(f"❌ Failed to create repo", parse_mode="markdown")
    return ConversationHandler.END

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    file = update.message.document
    file_name = file.file_name
    msg = await update.message.reply_text(f"📥 Downloading `{file_name}`...", parse_mode="markdown")
    
    try:
        file_obj = await context.bot.get_file(file.file_id)
        # v20+ এ ফাইল ডাউনলোড করার সঠিক মেথড
        downloaded = await file_obj.download_as_bytearray()
        
        await msg.edit_text(f"⏳ Uploading to Hugging Face...", parse_mode="markdown")
        success = await hf_upload_file(HF_REPO, file_name, bytes(downloaded))
        
        if success:
            await msg.edit_text(f"✅ File uploaded successfully: `{file_name}`", parse_mode="markdown")
        else:
            await msg.edit_text("❌ Upload failed", parse_mode="markdown")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:100]}", parse_mode="markdown")

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    await update.message.reply_text(
        "📖 **Commands Help**\n\n"
        "/start - Start bot\n"
        "/info - Repository information\n"
        "/files - List all files\n"
        "/write - Write/edit file\n"
        "/delete_file [path] - Delete file\n"
        "/new_repo - Create new repository\n"
        "/help - Show this help\n\n"
        "**Shortcut:** বটের ইনবক্সে যেকোনো ফাইল সরাসরি পাঠালে তা সরাসরি HF রেপোতে আপলোড হয়ে যাবে।",
        parse_mode="markdown"
    )

# ============================================================
# MAIN APPLICATION
# ============================================================
def main():
    # রেন্ডার সার্ভার পোর্ট সচল রাখার জন্য থ্রেড স্টার্ট
    threading.Thread(target=run_health_server, daemon=True).start()
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("files", files))
    app.add_handler(CommandHandler("delete_file", delete_file))
    app.add_handler(CommandHandler("help", help_cmd))
    
    # ইন্টারেক্টিভ রাইট কনভারসেশন
    write_conv = ConversationHandler(
        entry_points=[CommandHandler("write", write_file_start)],
        states={
            CHOOSING: [MessageHandler(filters.TEXT & ~filters.COMMAND, write_file_path)],
            WRITING_CONTENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, write_file_content)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(write_conv)
    
    # নিউ রেপো ক্রিয়েশন কনভারসেশন
    new_repo_conv = ConversationHandler(
        entry_points=[CommandHandler("new_repo", new_repo_start)],
        states={
            REPO_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_repo_name)],
            REPO_PRIVACY: [CallbackQueryHandler(new_repo_privacy)],
        },
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(new_repo_conv)
    
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    
    print(f"[+] HF Manager Bot Running on Port {PORT}")
    app.run_polling()

if __name__ == "__main__":
    main()
