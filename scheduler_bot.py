import os
import json
import asyncio
from threading import Thread
import discord
import time
import requests
import websockets

# Additional Selenium imports for cookie refresh.
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Globals
notifier = None
DISCORD_TOKEN = ""
CHANNEL_NAME = ""
ACC_ID = ""
SWAP_FROM = ""
SWAP_TO = ""
COOKIE = ""
TYPE = ""
COURSES = []  # List of course group dicts, each with keys "course" and "crns"
DC_PING_NAME = ""
USERNAME = ""
PASSWORD = ""

CONFIG_DIR = os.path.join(os.environ["LOCALAPPDATA"], "TAMUClassSwap")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

socket_url = "wss://api.collegescheduler.com/socket.io/?EIO=3&transport=websocket"
token = ""
TERM = ""
TERM_ID = ""

driver = None

# Global flag to control monitoring loops.
MONITOR_ACTIVE = True

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found at: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r") as config_file:
        return json.load(config_file)

def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

def refresh_cookie():
    global driver
    print("Refreshing cookie...")
    """
    Refresh the cookie using a headless browser to simulate a full login flow.
    This function logs in to CollegeScheduler using Microsoft SSO,
    retrieves the correct cookies from a protected page, saves them to config,
    and then quits the browser.
    Adjust element locators, URLs, and waits as needed.
    """
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    
    if not driver:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 30)
    
    try:
        # Step 1: Navigate to the entry page which triggers login.
        entry_url = "https://tamu.collegescheduler.com/entry"
        driver.get(entry_url)

        # Step 2: Look for the email field (loginfmt) to determine if login is needed.
        try:
            email_input = wait.until(EC.presence_of_element_located((By.NAME, "loginfmt")))
            email_input.clear()
            email_input.send_keys(USERNAME)
            email_input.send_keys(Keys.RETURN)
            time.sleep(3)
            password_input = wait.until(EC.presence_of_element_located((By.NAME, "passwd")))
            password_input.clear()
            password_input.send_keys(PASSWORD)
            password_input.send_keys(Keys.RETURN)
                                     
            try:
                yes_device_button = wait.until(EC.element_to_be_clickable((By.ID, "trust-browser-button")))
                driver.execute_script("arguments[0].click();", yes_device_button)
            except:
                notify_discord("Duo login failed. Manual intervention required. " + DC_PING_NAME)
                time.sleep(99999999)
            
            try:
                # Optionally handle "Stay signed in" prompt.
                stay_signed_in = wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9")))
                stay_signed_in.click()
            except Exception as e:
                print("Stay signed in prompt not encountered:", e)
        except Exception as e:
            print("Login form not found; may be already logged in:", e)

        # Step 3: Navigate to a protected page to force completion of the login flow.
        dashboard_url = "https://tamu.collegescheduler.com/dashboard"
        driver.get(dashboard_url)
        time.sleep(5)

        # Step 4: Extract cookies.
        cookies = driver.get_cookies()
        if cookies:
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            config_data = load_config()
            config_data["cookie"] = cookie_str
            save_config(config_data)
            global COOKIE
            COOKIE = cookie_str
            print("Cookie refreshed successfully using Selenium!")
            return cookie_str
        else:
            print("No cookies found after login.")
            return None
    except Exception as e:
        print("Error during Selenium login:", e)
        return None

def get_token():
    global token
    config = load_config()
    username = config.get("username")
    password = config.get("password")
    try:
        response = requests.get(
            "https://tamu.collegescheduler.com/api/oauth/student/client-credentials/token",
            headers={"Cookie": COOKIE}
        )
        response.raise_for_status()
        token = response.json()["accessToken"]
    except Exception as e:
        print(f"Error obtaining token: {e}")
        new_cookie = refresh_cookie()
        if new_cookie:
            try:
                response = requests.get(
                    "https://tamu.collegescheduler.com/api/oauth/student/client-credentials/token",
                    headers={"Cookie": new_cookie}
                )
                response.raise_for_status()
                token = response.json()["accessToken"]
            except Exception as e2:
                print(f"Error obtaining token after refreshing cookie: {e2}")
        else:
            print("Could not refresh cookie.")

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
                for course_group in COURSES:
                    course_str = course_group.get("course", "")
                    crn_list = course_group.get("crns", [])
                    if not course_str or not crn_list:
                        continue
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
                        # Attempt automatic cookie refresh once and continue.
                        refresh_cookie()
                        continue
                await asyncio.sleep(5)
            print("Monitoring stopped.")
            return

def notify_discord(message):
    if notifier:
        asyncio.run_coroutine_threadsafe(notifier.send_message(message), notifier.loop)

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

def start_monitoring():
    global notifier, DISCORD_TOKEN, CHANNEL_NAME, ACC_ID, DC_PING_NAME
    global SWAP_FROM, SWAP_TO, COOKIE, TYPE, COURSES, TERM, TERM_ID, MONITOR_ACTIVE, USERNAME, PASSWORD

    MONITOR_ACTIVE = True

    config = load_config()
    DISCORD_TOKEN = config.get("discord_token", "")
    CHANNEL_NAME = config.get("channel_name", "")
    ACC_ID = config.get("discord_account_id", "")
    SWAP_FROM = config.get("swap_from", "")
    SWAP_TO = config.get("swap_to", "")
    COOKIE = config.get("cookie", "")
    TYPE = config.get("type", "")
    COURSES = config.get("courses", [])
    TERM = config.get("term_name", "")
    USERNAME = config.get("username", "")
    PASSWORD = config.get("password", "")

    try:
        term_response = requests.get("https://tamu.collegescheduler.com/api/terms", headers={"Cookie": COOKIE})
        term_response.raise_for_status()
        terms = term_response.json()
        TERM_ID = next((t["code"] for t in terms if t["title"] == TERM), "")
        if not TERM_ID:
            raise Exception("TERM_ID not found")
    except Exception as e:
        print(f"Failed to fetch TERM_ID: {e}")
        new_cookie = refresh_cookie()
        if new_cookie:
            try:
                term_response = requests.get("https://tamu.collegescheduler.com/api/terms", headers={"Cookie": new_cookie})
                term_response.raise_for_status()
                terms = term_response.json()
                TERM_ID = next((t["code"] for t in terms if t["title"] == TERM), "")
            except Exception as e2:
                print("Cannot get TERM_ID after refreshing cookie:", e2)
                return
        else:
            print("Failed to refresh cookie for TERM_ID. Exiting.")
            return

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