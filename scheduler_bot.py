import os
import json
import asyncio
import concurrent.futures
import discord
import time
import pickle
import shutil
from threading import Thread, Event
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Globals
stop_event = Event()
clr_session = False
done = False
notifier = None
USERNAME = ""
PASSWORD = ""
CLASS_NAMES = []
DISCORD_TOKEN = ""
CHANNEL_NAME = ""
TERM_NAME = ""
REG_TIME = ""
ACC_ID = ""
HEADLESS = False
AUTO_REGISTER = False
driver = None
DC_PING_NAME = ""

CONFIG_DIR = os.path.join(os.environ["LOCALAPPDATA"], "TAMUCheckSeats")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise FileNotFoundError(f"Config file not found at: {CONFIG_PATH}")
    with open(CONFIG_PATH, 'r') as config_file:
        return json.load(config_file)

class DiscordNotifier(discord.Client):
    def __init__(self, channel_id):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    async def on_ready(self):
        print(f'Logged in as {self.user}')

    async def send_message(self, message):
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.name == CHANNEL_NAME:
                    await channel.send(message)
                    break

    def start_bot(self, token):
        self.loop.create_task(self.start(token))
        Thread(target=self.loop.run_forever, daemon=True).start()

def notify_discord(message):
    if notifier:
        asyncio.run_coroutine_threadsafe(notifier.send_message(message), notifier.loop)

def try_register(driver, wait):
    try:
        register_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Register')]")))
        print("Clicking Register...")
        driver.execute_script("arguments[0].click();", register_btn)

        confirm_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Continue')]")))
        print("Clicking Continue to confirm registration...")
        driver.execute_script("arguments[0].click();", confirm_btn)
        notify_discord("✅ Successfully registered for your shopping cart! " + DC_PING_NAME)
        driver.quit()
        return True
    except Exception as e:
        print(f"Failed to register: {e}")
        return False

def check_all_seats_open(driver):
    print("Checking if all shopping cart seats are open...")

    try:
        # Find all rows in the shopping cart
        rows = driver.find_elements(By.XPATH, "//table//tbody[contains(@class, 'groupCss')]//tr")

        if not rows:
            print("No rows found in shopping cart table.")
            return False

        for row in rows:
            try:
                cells = row.find_elements(By.TAG_NAME, "td")
                if len(cells) >= 6:
                    seat_cell = cells[7]
                    seat_text = seat_cell.text.strip()
                    print(f"Found seat count: '{seat_text}'")
                    if not seat_text.isdigit() or int(seat_text) <= 0:
                        return False
            except Exception as e:
                print(f"Error reading row: {e}")
                return False
        return True
    except Exception as e:
        print(f"Error while checking seat availability: {e}")
        return False

    except Exception as e:
        print(f"Failed to parse shopping cart table: {e}")
        all_open = False

    return all_open


def login_collegescheduler():
    global clr_session, done, driver

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    if HEADLESS:
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")

    # Chrome session
    SESSION_DIR = r"C:\Temp\chrome_user_data"
    SESSION_PATH = os.path.join(SESSION_DIR, "profile")
    COOKIES_PATH = os.path.join(SESSION_DIR, "cookies.pkl")

    clr_session = True

    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR)
    options.add_argument(f"--user-data-dir={SESSION_PATH}")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)

    try:
        print("Starting login process.")
        cookies_loaded = False
        if os.path.exists(COOKIES_PATH):
            driver.get("https://tamu.collegescheduler.com/entry")
            try:
                with open(COOKIES_PATH, "rb") as cookies_file:
                    cookies = pickle.load(cookies_file)
                    for cookie in cookies:
                        driver.add_cookie(cookie)
                cookies_loaded = True
                print("Cookies loaded, attempting session.")
                driver.refresh()
            except Exception as e:
                print(f"Failed to load cookies: {e}")

        if not cookies_loaded:
            driver.get("https://tamu.collegescheduler.com/entry")

        global term_td
        term_td = None
        try:
            wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'btnLinkCss') and contains(text(), 'Change')]")))
            print("Already logged in (1)")
        except:
            try:
                wait.until(EC.element_to_be_clickable((By.XPATH, f"//td[contains(text(), '{TERM_NAME}')]")))
                print("Already logged in (2)")
            except:
                print("Logging in...")
                wait = WebDriverWait(driver, 30)
                email_input = wait.until(EC.presence_of_element_located((By.NAME, "loginfmt")))
                email_input.send_keys(USERNAME)
                email_input.send_keys(Keys.RETURN)

                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                time.sleep(3)

                password_input = wait.until(EC.presence_of_element_located((By.NAME, "passwd")))
                password_input.send_keys(PASSWORD)
                password_input.send_keys(Keys.RETURN)

                try:
                    yes_device_button = wait.until(EC.element_to_be_clickable((By.ID, "trust-browser-button")))
                    driver.execute_script("arguments[0].click();", yes_device_button)
                except:
                    notify_discord("Duo login failed. Manual intervention required. " + DC_PING_NAME)
                    time.sleep(99999999)

                try:
                    stay_signed_in_button = wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9")))
                    stay_signed_in_button.click()
                except:
                    pass

                with open(COOKIES_PATH, "wb") as cookies_file:
                    pickle.dump(driver.get_cookies(), cookies_file)

        while not stop_event.is_set():
            try:
                current_term = driver.find_element(By.XPATH, f"//div[contains(text(), '{TERM_NAME}')]")
            except:
                try:
                    change_button = driver.find_element(By.XPATH, "//a[starts-with(text(), 'Change')]")
                    driver.execute_script("arguments[0].click();", change_button)
                except Exception as e:
                    print(f"Change term error: {e}")

            try:
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                term_td = wait.until(EC.element_to_be_clickable((By.XPATH, f"//td[contains(text(), '{TERM_NAME}')]")))
                driver.execute_script("arguments[0].click();", term_td)

                save_continue_button = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[.//span[contains(text(), 'Save')] or contains(text(), 'Save and Continue')]")
                ))
                driver.execute_script("arguments[0].click();", save_continue_button)
            except Exception as e:
                print(f"Term select error: {e}")

            print(AUTO_REGISTER)

            if AUTO_REGISTER:
                print("Entered Auto Register Logic")

                # Wait until the registration time (epoch) has been reached
                cart_tab = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@aria-label, 'Shopping Cart contains')]")))
                driver.execute_script("arguments[0].click();", cart_tab)

                if REG_TIME:
                    now = time.time()
                    if now < float(REG_TIME):
                        wait_seconds = float(REG_TIME) - now
                        print(f"Waiting {int(wait_seconds)} seconds until registration time...")
                        time.sleep(wait_seconds)

                while not stop_event.is_set():
                    driver.refresh()
                    time.sleep(3)
                    if check_all_seats_open(driver):
                        print("All classes have seats available. Attempting to register.")
                        if try_register(driver, wait):
                            break
                    else:
                        print("Some classes still have 0 seats. Retrying...")
                        time.sleep(1)
            else:
                for CLASS_NAME in CLASS_NAMES:
                    try:
                        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                        sections_link = wait.until(EC.element_to_be_clickable((
                            By.XPATH, f"//a[contains(@aria-label, 'Sections for') and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{CLASS_NAME}')]"
                        )))
                        driver.execute_script("arguments[0].click();", sections_link)
                    except Exception as e:
                        print(f"Section link error: {e}")

                    try:
                        time.sleep(3)
                        rows = driver.find_elements(By.XPATH, "//tbody[contains(@class, 'groupCss')]//tr")
                        for row in rows:
                            try:
                                tds = row.find_elements(By.TAG_NAME, "td")
                                if len(tds) > 7:
                                    crn = tds[2].text.strip()
                                    seats_open = tds[7].text.strip()
                                    if int(seats_open) > 0:
                                        print(f"{crn} has {seats_open} seats open.")
                                        notify_discord(f"New opening: {tds[3].text.strip()}-{tds[4].text.strip()}-{tds[5].text.strip()} {crn} has {seats_open} seats! " + DC_PING_NAME)
                            except Exception as e:
                                print(f"Row error: {e}")
                    except Exception as e:
                        print(f"Availability check error: {e}")
                    try:
                        back_button = wait.until(EC.element_to_be_clickable((
                            By.XPATH, "//button[.//span[contains(text(), 'Save')] or contains(text(), 'Save and Continue')]"
                        )))
                        driver.execute_script("arguments[0].click();", back_button)
                    except:
                        print("Failed to go back.")
                print("Loop complete.")
    finally:
        done = True
        driver.quit()
        print("Done.")

def start_monitoring():
    global notifier, USERNAME, PASSWORD, CLASS_NAMES, DISCORD_TOKEN, CHANNEL_NAME, TERM_NAME, HEADLESS, AUTO_REGISTER, REG_TIME, ACC_ID, DC_PING_NAME, done

    config = load_config()
    USERNAME = config.get('username')
    PASSWORD = config.get('password')
    CLASS_NAMES = [name.lower() for name in config.get('class_names', [])]
    DISCORD_TOKEN = config.get('discord_token')
    CHANNEL_NAME = config.get('channel_name')
    TERM_NAME = config.get('term_name')
    REG_TIME = config.get('reg_time')
    ACC_ID = config.get('discord_account_id')
    HEADLESS = config.get('headless', False)
    AUTO_REGISTER = config.get('auto_register', False)

    notifier = DiscordNotifier(CHANNEL_NAME)
    notifier.start_bot(DISCORD_TOKEN)

    if ACC_ID != None:
        DC_PING_NAME = "<@"+ACC_ID+">"

    with concurrent.futures.ThreadPoolExecutor() as executor:
        while not stop_event.is_set():
            executor.submit(login_collegescheduler)
            print("Submitted task to check seat availability.")
            while not done and not stop_event.is_set():
                time.sleep(1)
            done = False

if __name__ == "__main__":
    start_monitoring()