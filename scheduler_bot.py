# scheduler_bot.py
import os
import json
import time
import requests
import asyncio
import websockets
from threading import Thread
import discord

# ───── Selenium imports for cookie‑refresh in swap only ─────
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ───── GLOBAL CONFIG ─────
CONFIG_DIR    = os.path.join(os.environ["LOCALAPPDATA"], "TAMUClassSwap")
CONFIG_PATH   = os.path.join(CONFIG_DIR, "config.json")
socket_url    = "wss://api.collegescheduler.com/socket.io/?EIO=3&transport=websocket"

# THESE ARE USED FOR “watch” MODE:
CRNS_TO_WATCH = []     # will be loaded from config
INTERVAL      = 5      # seconds between checks

# THESE ARE LOADED FOR “swap” MODE:
SWAP_FROM      = ""
SWAP_TO        = ""
COOKIE         = ""
USERNAME       = ""
PASSWORD       = ""
TERM           = ""
TERM_ID        = ""
token          = ""
TYPE           = ""       # "watch" or "swap"
DISCORD_TOKEN  = ""
CHANNEL_NAME   = ""
ACC_ID         = ""
DC_PING_NAME   = ""
notifier       = None
driver         = None
MONITOR_ACTIVE = True


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file missing: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def save_config(cfg):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)


# ───── WATCH MODE FUNCTIONS ─────
def fetch_all_sections(session):
    url = "https://howdy.tamu.edu/api/course-sections"
    payload = {
        "startRow":     0,
        "endRow":       0,    # fetch everything
        "termCode":    TERM_ID,
        "publicSearch": "Y"
    }
    resp = session.post(url, json=payload, headers={"Cookie": COOKIE}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else data.get("courseSections", [])


def monitor_crns():
    """Lightweight loop: hit howdy API every INTERVAL seconds, print status of CRNS_TO_WATCH."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    watch_crns = [str(c) for c in CRNS_TO_WATCH]
    print(f"Starting WATCH mode: checking CRNs {watch_crns} every {INTERVAL}s\n")

    while True:
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            records = fetch_all_sections(session)
        except Exception as e:
            print(f"[{now}] ERROR fetching sections:", e)
            time.sleep(INTERVAL)
            continue

        # DEBUG: how many records did we get? what keys do they carry?
        print(f"[{now}] DEBUG: fetched {len(records)} sections")

        # build a map CRN→info
        status_map = {}
        for r in records:
            crn_val = r.get("SWV_CLASS_SEARCH_CRN")
            crn     = str(crn_val) if crn_val is not None else None
            is_open = (r.get("STUSEAT_OPEN") == "Y")
            title   = f"{r.get('SWV_CLASS_SEARCH_SUBJECT')} {r.get('SWV_CLASS_SEARCH_COURSE')} – {r.get('SWV_CLASS_SEARCH_TITLE')}"
            if crn:
                status_map[crn] = {"open": is_open, "title": title}

        # now report on each watched CRN
        for crn in watch_crns:
            info = status_map.get(crn)
            if info:
                status = "🔓 OPEN" if info["open"] else "🔒 Full"
                print(f"[{now}] CRN {crn} ({info['title']}): {status}")
                if info["open"]:
                    notify_discord(f"[{now}] CRN {crn} ({info['title']}): {status}")
            else:
                print(f"[{now}] CRN {crn}: ❓ not found")

        time.sleep(INTERVAL)


# ───── SWAP MODE FUNCTIONS ─────
def refresh_cookie():
    global driver, COOKIE
    print("Refreshing cookie via Selenium…")
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("user-agent=Mozilla/5.0")

    if not driver:
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=opts
        )
    wait = WebDriverWait(driver, 30)

    driver.get("https://tamu.collegescheduler.com/entry")
    # … login flow as before …
    driver.get("https://tamu.collegescheduler.com/dashboard")
    time.sleep(3)
    cookies = driver.get_cookies()
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    cfg = load_config()
    cfg["cookie"] = cookie_str
    save_config(cfg)
    COOKIE = cookie_str
    print("Cookie refreshed!")
    return cookie_str


def get_token():
    global token
    try:
        resp = requests.get(
            "https://tamu.collegescheduler.com/api/oauth/student/client-credentials/token",
            headers={"Cookie": COOKIE},
            timeout=10
        )
        resp.raise_for_status()
        token = resp.json()["accessToken"]
    except:
        new_ck = refresh_cookie()
        if new_ck:
            resp = requests.get(
                "https://tamu.collegescheduler.com/api/oauth/student/client-credentials/token",
                headers={"Cookie": new_ck},
                timeout=10
            )
            resp.raise_for_status()
            token = resp.json()["accessToken"]


async def send_message():
    global MONITOR_ACTIVE

    async with websockets.connect(socket_url) as ws:
        get_token()
        while MONITOR_ACTIVE:
            await ws.send(f'420["authorize",{{"token":"{token}"}}]')
            await ws.send(
                f'421["registration-request",{{'
                f'"subdomain":"tamu","type":"ENROLL_CART","userId":0,'
                f'"termCode":"{TERM_ID}",'
                f'"regNumberRequests":['
                    f'{{"regNumber":"{SWAP_FROM}","action":"DW"}},'
                    f'{{"regNumber":"{SWAP_TO}"}}'
                f'],'
                f'"additionalData":{{"altPin":""}},"conditionalAddDrop":"Y"'
                f'}}]'
            )
            await asyncio.sleep(1)

        print("Swap monitor ended.")


def notify_discord(message):
    if notifier:
        asyncio.run_coroutine_threadsafe(notifier.send_message(message), notifier.loop)


class DiscordNotifier(discord.Client):
    def __init__(self, channel_name):
        super().__init__(intents=discord.Intents.default())
        self.channel_name = channel_name

    async def on_ready(self):
        print(f"Discord bot logged in as {self.user}")

    async def send_message(self, message):
        for guild in self.guilds:
            chan = discord.utils.get(guild.text_channels, name=self.channel_name)
            if chan:
                await chan.send(message)
                return

    def start_bot(self, token):
        Thread(target=lambda: asyncio.run(self.start(token)), daemon=True).start()


# ───── ENTRY POINT ─────
def start_monitoring():
    global notifier, SWAP_FROM, SWAP_TO, COOKIE, USERNAME, PASSWORD
    global TERM, TERM_ID, TYPE, CRNS_TO_WATCH
    global DISCORD_TOKEN, CHANNEL_NAME, ACC_ID, DC_PING_NAME

    cfg = load_config()
    TYPE           = cfg.get("type", "")
    DISCORD_TOKEN  = cfg.get("discord_token", "")
    CHANNEL_NAME   = cfg.get("channel_name", "")
    ACC_ID         = cfg.get("discord_account_id", "")
    SWAP_FROM      = cfg.get("swap_from", "")
    SWAP_TO        = cfg.get("swap_to", "")
    COOKIE         = cfg.get("cookie", "")
    USERNAME       = cfg.get("username", "")
    PASSWORD       = cfg.get("password", "")
    TERM           = cfg.get("term_name", "")
    CRNS_TO_WATCH  = cfg.get("crns_to_watch", [])

    # ─── Fetch all terms and build desc→code map ───
    try:
        resp = requests.get(
            "https://howdy.tamu.edu/api/all-terms",
            headers={"Cookie": COOKIE},
            timeout=10
        )
        resp.raise_for_status()
        all_terms = resp.json()
        term_map = {
            t["STVTERM_DESC"]: t["STVTERM_CODE"]
            for t in all_terms
            if "STVTERM_DESC" in t and "STVTERM_CODE" in t
        }
        TERM_ID = term_map.get(TERM, "")
        if not TERM_ID:
            print(f"[start_monitoring] Warning: could not find term code for '{TERM}'")
        else:
            print(f"[start_monitoring] Using term code {TERM_ID} for '{TERM}'")
    except Exception as e:
        TERM_ID = ""
        print(f"[start_monitoring] Error fetching term list: {e}")


    # ─── Setup Discord notifier ───
    notifier = DiscordNotifier(CHANNEL_NAME)
    if DISCORD_TOKEN:
        notifier.start_bot(DISCORD_TOKEN)
    if ACC_ID:
        DC_PING_NAME = f"<@{ACC_ID}>"

    # ─── Kick off the right monitor loop ───
    if TYPE == "watch":
        monitor_crns()
    elif TYPE == "swap":
        asyncio.run(send_message())
    else:
        print("Invalid type in config; must be 'watch' or 'swap'.")


def stop_monitoring():
    global MONITOR_ACTIVE
    MONITOR_ACTIVE = False
    print("Monitoring stopped by user.")


if __name__ == "__main__":
    start_monitoring()