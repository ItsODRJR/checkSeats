import os
import json
import asyncio
from threading import Thread
import discord
import time
import requests
import websockets

# Globals
notifier = None
DISCORD_TOKEN = ""
CHANNEL_NAME = ""
ACC_ID = ""
SWAP_FROM = ""
SWAP_TO = ""
COOKIE = ""
TYPE = ""
COURSES = []  # New global; list of course groups, each with "course" and "crns"
DC_PING_NAME = ""

CONFIG_DIR = os.path.join(os.environ["LOCALAPPDATA"], "TAMUClassSwap")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

socket_url = "wss://api.collegescheduler.com/socket.io/?EIO=3&transport=websocket"
token = ""
TERM = ""
TERM_ID = ""

# Global flag to control monitoring loops.
MONITOR_ACTIVE = True

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found at: {CONFIG_PATH}")
    with open(CONFIG_PATH, 'r') as config_file:
        return json.load(config_file)

class DiscordNotifier(discord.Client):
    def __init__(self, channel_name):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.channel_name = channel_name

    async def on_ready(self):
        print(f"Discord bot connected as {self.user}")

    async def send_message(self, message):
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == self.channel_name:
                    await channel.send(message)
                    return

    def start_bot(self, token):
        Thread(target=lambda: asyncio.run(self.start(token)), daemon=True).start()

def notify_discord(message):
    if notifier:
        asyncio.run_coroutine_threadsafe(notifier.send_message(message), notifier.loop)

def get_token():
    global token
    try:
        response = requests.get("https://tamu.collegescheduler.com/api/oauth/student/client-credentials/token",
                                headers={"Cookie": COOKIE})
        response.raise_for_status()
        token = response.json()["accessToken"]
    except Exception as e:
        print(f"Error obtaining token: {e}")

async def send_message():
    global MONITOR_ACTIVE
    async with websockets.connect(socket_url) as websocket:
        if TYPE == "swap":
            while MONITOR_ACTIVE:
                await websocket.send(f'420["authorize",{{"token":"{token}"}}]')
                await websocket.send(
                    f'421["registration-request",{{"subdomain":"tamu","type":"ENROLL_CART","userId":0,"termCode":"{TERM_ID}","regNumberRequests":[{{"regNumber":"{SWAP_FROM}","action":"DW"}},{{"regNumber":"{SWAP_TO}"}}],"additionalData":{{"altPin":""}},"conditionalAddDrop":"Y"}}]'
                )
                while MONITOR_ACTIVE:
                    try:
                        # Use a timeout so the loop periodically checks the stop flag.
                        msg = await asyncio.wait_for(websocket.recv(), timeout=1)
                    except asyncio.TimeoutError:
                        continue

                    if not MONITOR_ACTIVE:
                        break

                    if "REGISTRATION_FAILURE" in msg:
                        try:
                            payload = json.loads(msg.split("42", 1)[1])
                            reg_responses = payload[1].get("regNumberResponses", [])
                            failure_message = next(
                                (m["message"] for r in reg_responses for m in r.get("sectionMessages", [])
                                 if "closed section" in m["message"].lower()), "Unknown error")
                        except Exception:
                            failure_message = "Unknown error"
                        print(f"Failed to register: {failure_message}. Retrying...")
                        await asyncio.sleep(2)
                        break
                    elif "TokenExpiredError" in msg:
                        print("Token expired, retrying...")
                        get_token()
                    elif '"status":"REGISTERED"' in msg:
                        notify_discord(f"{DC_PING_NAME} {SWAP_FROM} swapped with {SWAP_TO}.")
                        print("Swap successful – ending monitor.")
                        MONITOR_ACTIVE = False
                        break
                if not MONITOR_ACTIVE:
                    break
            print("Monitoring stopped.")
            return

        elif TYPE == "watch":
            while MONITOR_ACTIVE:
                # For each course group in the config
                for course_group in COURSES:
                    course_str = course_group.get("course", "")
                    crn_list = course_group.get("crns", [])
                    if not course_str or not crn_list:
                        continue  # Skip if incomplete
                    parts = course_str.split(" ")
                    if len(parts) < 2:
                        print(f"Invalid course format: {course_str}")
                        continue
                    subject = parts[0]
                    course_number = parts[1]
                    url = f"https://tamu.collegescheduler.com/api/terms/{TERM}/subjects/{subject}/courses/{course_number}/regblocks"
                    try:
                        response = requests.get(url, headers={"Cookie": COOKIE})
                        response.raise_for_status()
                        regblocks = response.json()
                        sections = regblocks.get("sections", [])
                        for crn in crn_list:
                            for section in sections:
                                if str(section.get("registrationNumber")) == str(crn):
                                    seats = section.get("openSeats", 0)
                                    if seats > 0:
                                        notify_discord(f"{DC_PING_NAME} CRN {crn} in course {course_str} has {seats} open seat(s)!")
                                        print(f"Notified: CRN {crn} in course {course_str} now has {seats} open seat(s).")
                                        break
                                    else:
                                        print(f"CRN {crn} in course {course_str} has 0 open seats.")
                                    break
                            else:
                                print(f"CRN {crn} not found in regblocks for course {course_str}.")
                    except Exception as e:
                        print(f"Error checking course {course_str}: {e}")
                await asyncio.sleep(5)
            print("Monitoring stopped.")
            return

def start_monitoring():
    global notifier, DISCORD_TOKEN, CHANNEL_NAME, ACC_ID, DC_PING_NAME
    global SWAP_FROM, SWAP_TO, COOKIE, TYPE, COURSES, TERM, TERM_ID, MONITOR_ACTIVE

    # Reset the monitoring flag on start.
    MONITOR_ACTIVE = True

    config = load_config()
    DISCORD_TOKEN = config.get("discord_token", "")
    CHANNEL_NAME = config.get("channel_name", "")
    ACC_ID = config.get("discord_account_id", "")
    SWAP_FROM = config.get("swap_from", "")
    SWAP_TO = config.get("swap_to", "")
    COOKIE = config.get("cookie", "")
    TYPE = config.get("type", "")
    COURSES = config.get("courses", [])  # New structure for watch mode
    TERM = config.get("term_name", "")

    try:
        term_response = requests.get("https://tamu.collegescheduler.com/api/terms", headers={"Cookie": COOKIE})
        term_response.raise_for_status()
        terms = term_response.json()
        TERM_ID = next((term["code"] for term in terms if term["title"] == TERM), "")
    except Exception as e:
        print(f"Failed to fetch TERM_ID: {e}")
        TERM_ID = ""

    notifier = DiscordNotifier(CHANNEL_NAME)
    notifier.start_bot(DISCORD_TOKEN)

    if ACC_ID:
        DC_PING_NAME = f"<@{ACC_ID}>"

    get_token()
    asyncio.run(send_message())

def stop_monitoring():
    global MONITOR_ACTIVE
    MONITOR_ACTIVE = False
    try:
        print("Stop monitoring requested.")
    except Exception as e:
        print(f"Error sending stop notification: {e}")

if __name__ == "__main__":
    start_monitoring()