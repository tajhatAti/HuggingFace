import os
import asyncio
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# Telethon Modules
from telethon import TelegramClient, events, Button
# Hugging Face API Modules (এটিই সবচেয়ে ইম্পর্ট্যান্ট)
from huggingface_hub import HfApi

# Async HTTP (বাকি টুকটাক রিকোয়েস্টের জন্য)
import aiohttp


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
API_ID = int(os.environ.get("API_ID", "0"))      # তোমার API ID
API_HASH = os.environ.get("API_HASH", "")        # তোমার API HASH
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))  # তোমার টেলিগ্রাম আইডি
HF_TOKEN = os.environ.get("HF_TOKEN", "")
HF_REPO = os.environ.get("HF_REPO", "")
HF_USERNAME = os.environ.get("HF_USERNAME", "Madarauchihagmailcom")
HF_TYPE = os.environ.get("HF_TYPE", "space")
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
    except Exception:
        return None

async def hf_upload_file(repo_id, path, content):
    try:
        # রানার থ্রেডে সিঙ্ক আপলোড হ্যান্ডেল করা
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: api.upload_file(
                path_or_fileobj=content if isinstance(content, bytes) else content.encode("utf-8"),
                path_in_repo=path,
                repo_id=repo_id,
                repo_type=HF_TYPE,
                token=HF_TOKEN
            )
        )
        return True
    except Exception:
        return False

async def hf_delete_file(repo_id, path):
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: api.delete_file(
                path_in_repo=path,
                repo_id=repo_id,
                repo_type=HF_TYPE,
                token=HF_TOKEN
            )
        )
        return True
    except Exception:
        return False

async def hf_create_repo(repo_id, private=False):
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: api.create_repo(
                repo_id=repo_id,
                repo_type=HF_TYPE,
                private=private,
                token=HF_TOKEN
            )
        )
        return True
    except Exception:
        return False

async def hf_get_repo_info(repo_id):
    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(
            None,
            lambda: api.repo_info(repo_id=repo_id, repo_type=HF_TYPE)
        )
        return info
    except Exception:
        return None

# ============================================================
# TELETHON CLIENT SETUP
# ============================================================
# বটের জন্য মেমোরি সেশন ব্যবহার করা হচ্ছে যেন রেন্ডারে কোনো ফাইল লকের ঝামেলা না হয়
bot = TelegramClient('hf_bot_session', API_ID, API_HASH)

# ইউজার স্টেট ট্র্যাকিং (Conversation এর বিকল্প)
user_states = {}

# সেশন ক্লিয়ারেন্স ও সিকিউরিটি চেক
def is_owner(sender_id):
    return sender_id == OWNER_ID

# ============================================================
# BOT EVENTS / HANDLERS
# ============================================================

@bot.on(events.NewMessage(pattern='/start'))
async def start(event):
    if not is_owner(event.sender_id): return
    await event.respond(
        "🤖 **Hugging Face Repo Manager Bot (Telethon)**\n\n"
        "/info - Repository info\n"
        "/files - Browse files\n"
        "/write - Write/edit file\n"
        "/delete_file - Delete file\n"
        "/new_repo - Create new repo\n"
        "/help - Commands help",
        parse_mode="markdown"
    )

@bot.on(events.NewMessage(pattern='/info'))
async def info(event):
    if not is_owner(event.sender_id): return
    msg = await event.respond("⏳ Fetching repository info...")
    
    info_data = await hf_get_repo_info(HF_REPO)
    if not info_data:
        await msg.edit("❌ Could not fetch repo info")
        return
    
    private = getattr(info_data, 'private', False)
    created_at = getattr(info_data, 'created_at', "Unknown")
    updated_at = getattr(info_data, 'last_modified', "Unknown")
    
    text = (
        f"📦 **{HF_REPO}**\n\n"
        f"🔒 Privacy: `{'Private' if private else 'Public'}`\n"
        f"📅 Created: `{created_at}`\n"
        f"⏱️ Updated: `{updated_at}`\n"
        f"🔗 [View on HF](https://huggingface.co/{HF_REPO})"
    )
    await msg.edit(text, parse_mode="markdown")

@bot.on(events.NewMessage(pattern='/files'))
async def files(event):
    if not is_owner(event.sender_id): return
    msg = await event.respond("⏳ Loading files...")
    
    items = await hf_list_repo_tree(HF_REPO, path="")
    if items is None:
        await msg.edit("❌ Could not load files")
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
            
    await msg.edit(text, parse_mode="markdown")

# ইন্টারেক্টিভ কন্টেন্ট রাইটিং মডিউল
@bot.on(events.NewMessage(pattern='/write'))
async def write_start(event):
    if not is_owner(event.sender_id): return
    user_states[event.sender_id] = {'state': 'waiting_path'}
    await event.respond("📝 Send file path (e.g. `app/main.py`):")

@bot.on(events.NewMessage(pattern='/new_repo'))
async def new_repo_start(event):
    if not is_owner(event.sender_id): return
    user_states[event.sender_id] = {'state': 'waiting_repo_name'}
    await event.respond("📦 **Create New Repository**\n\nSend repo name (e.g. `my-awesome-space`):")

@bot.on(events.NewMessage(pattern='/delete_file'))
async def delete_file_cmd(event):
    if not is_owner(event.sender_id): return
    args = event.message.text.split(' ', 1)
    if len(args) < 2:
        await event.respond("❌ Format: /delete_file [path]\nExample: `/delete_file test.py`")
        return
    
    file_path = args[1].strip()
    msg = await event.respond(f"⏳ Deleting `{file_path}`...")
    success = await hf_delete_file(HF_REPO, file_path)
    
    if success:
        await msg.edit(f"✅ File deleted: `{file_path}`")
    else:
        await msg.edit("❌ Could not delete file")

# কলব্যাক কুয়েরি হ্যান্ডলার (প্রাইভেসি সিলেক্ট করার বাটন)
@bot.on(events.CallbackQuery(pattern=r'privacy:'))
async def new_repo_privacy(event):
    if not is_owner(event.sender_id): return
    privacy = event.data.decode('utf-8').split(":")[1]
    is_private = privacy == "private"
    
    state_data = user_states.get(event.sender_id, {})
    repo_name = state_data.get('repo_name')
    
    if not repo_name:
        await event.edit("❌ Session expired. Try again.")
        return
        
    await event.edit(f"⏳ Creating repo `{repo_name}` ({privacy})...")
    
    full_repo_id = f"{HF_USERNAME}/{repo_name}"
    success = await hf_create_repo(full_repo_id, private=is_private)
    
    if success:
        await event.edit(
            f"✅ Repository created!\n\n"
            f"📦 **{full_repo_id}**\n"
            f"🔗 [View on HF](https://huggingface.co/{HF_TYPE}s/{full_repo_id})"
        )
    else:
        await event.edit("❌ Failed to create repo")
    
    user_states.pop(event.sender_id, None)

# নরমাল টেক্সট / মেসেজ হ্যান্ডলার (স্টেট অনুযায়ী কাজ করবে)
@bot.on(events.NewMessage)
async def handle_all_messages(event):
    if not is_owner(event.sender_id) or event.message.text.startswith('/'): return
    
    state_data = user_states.get(event.sender_id)
    if not state_data: return
    
    current_state = state_data.get('state')
    
    if current_state == 'waiting_path':
        user_states[event.sender_id]['file_path'] = event.message.text.strip()
        user_states[event.sender_id]['state'] = 'waiting_content'
        await event.respond(f"✍️ Send content for `{event.message.text.strip()}`:")
        
    elif current_state == 'waiting_content':
        file_path = state_data.get('file_path')
        content = event.message.text
        
        msg = await event.respond(f"⏳ Uploading `{file_path}`...")
        success = await hf_upload_file(HF_REPO, file_path, content)
        
        if success:
            await msg.edit(f"✅ File updated: `{file_path}`")
        else:
            await msg.edit("❌ Failed to upload file")
        user_states.pop(event.sender_id, None)
        
    elif current_state == 'waiting_repo_name':
        repo_name = event.message.text.strip()
        user_states[event.sender_id]['repo_name'] = repo_name
        user_states[event.sender_id]['state'] = 'waiting_privacy'
        
        # টেলিথনের নিজস্ব কিবোর্ড বাটন মেথড
        buttons = [
            [Button.inline("🌐 Public", b"privacy:public"),
             Button.inline("🔒 Private", b"privacy:private")]
        ]
        await event.respond(f"🔒 Choose privacy for `{repo_name}`:", buttons=buttons)

# ডকুমেন্ট বা যেকোনো ফাইল আপলোড হ্যান্ডলার
@bot.on(events.NewMessage(func=lambda e: e.document))
async def handle_document(event):
    if not is_owner(event.sender_id): return
    
    file_name = event.message.document.attributes[0].file_name
    msg = await event.respond(f"📥 Downloading `{file_name}`...")
    
    try:
        # মেমরিতে ফাইল ডাউনলোড
        downloaded = await bot.download_media(event.message.document, bytes)
        await msg.edit("⏳ Uploading to Hugging Face...")
        
        success = await hf_upload_file(HF_REPO, file_name, downloaded)
        if success:
            await msg.edit(f"✅ File uploaded successfully: `{file_name}`")
        else:
            await msg.edit("❌ Upload failed")
    except Exception as e:
        await msg.edit(f"❌ Error: {str(e)[:100]}")

@bot.on(events.NewMessage(pattern='/help'))
async def help_cmd(event):
    if not is_owner(event.sender_id): return
    await event.respond(
        "📖 **Commands Help**\n\n"
        "/start - Start bot\n"
        "/info - Repository information\n"
        "/files - List all files\n"
        "/write - Write/edit file\n"
        "/delete_file [path] - Delete file\n"
        "/new_repo - Create new repository\n"
        "/help - Show this help\n\n"
        "**Shortcut:** বটের ইনবক্সে যেকোনো ফাইল সরাসরি পাঠালে তা সরাসরি HF রেপোতে আপলোড হয়ে যাবে।"
    )

# ============================================================
# MAIN EXECUTION
# ============================================================
def main():
    # রান হেলথ সার্ভার (Render keep-alive)
    threading.Thread(target=run_health_server, daemon=True).start()
    
    print(f"[+] HF Manager Bot (Telethon) Running on Port {PORT}")
    bot.start(bot_token=BOT_TOKEN)
    bot.run_until_disconnected()

if __name__ == "__main__":
    main()
        
