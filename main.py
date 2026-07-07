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