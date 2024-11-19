import os
import json
import asyncio
import concurrent.futures
from threading import Thread
import discord
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import pickle
import shutil
clr_session = False
done = False

# Load configuration
def load_config():
    with open('config.json', 'r') as config_file:
        return json.load(config_file)

config = load_config()
USERNAME = config['username']
PASSWORD = config['password']
CLASS_NAMES = [name.lower() for name in config['class_names']]
DISCORD_TOKEN = config['discord_token']
CHANNEL_ID = config['channel_id']

# Discord bot setup
class DiscordNotifier(discord.Client):
    def __init__(self, channel_id):
        intents = discord.Intents.default()
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.loop = asyncio.get_event_loop()

    async def on_ready(self):
        print(f'Logged in as {self.user}')

    async def send_message(self, message):
        for guild in self.guilds:
            for channel in guild.text_channels:
                if channel.id:
                    print("Bet")
                    channel = self.get_channel(channel.id)
                    await channel.send(message)
                    break

    def start_bot(self, token):
        self.loop.create_task(self.start(token))
        Thread(target=self.loop.run_forever, daemon=True).start()

notifier = DiscordNotifier(CHANNEL_ID)
notifier.start_bot(DISCORD_TOKEN)

def notify_discord(message):
    asyncio.run_coroutine_threadsafe(notifier.send_message(message), notifier.loop)

def login_collegescheduler():
    global clr_session
    global done
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")
    options.add_argument("--headless")

    # Chrome user session setup
    SESSION_DIR = os.path.join("/tmp", "chrome_user_data")
    SESSION_PATH = os.path.join(SESSION_DIR, "profile")
    COOKIES_PATH = os.path.join(SESSION_DIR, "cookies.pkl")

    def clear_session():
       if os.path.exists(SESSION_PATH):
            shutil.rmtree(SESSION_PATH)
            print("Previous Chrome session cleared.")
    
    if clr_session:  
        clear_session()  

    clr_session = True 

    if not os.path.exists(SESSION_DIR):
        os.makedirs(SESSION_DIR)
    options.add_argument(f"--user-data-dir={SESSION_PATH}")

    # Install and use ChromeDriver
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)

    try:
        print("Starting login process.")
        
        cookies_loaded = False
        if os.path.exists(COOKIES_PATH):
            driver.get("https://tamu.collegescheduler.com")
            try:
                with open(COOKIES_PATH, "rb") as cookies_file:
                    cookies = pickle.load(cookies_file)
                    for cookie in cookies:
                        driver.add_cookie(cookie)
                cookies_loaded = True
                print("Cookies loaded, attempting to access the site with saved session.")
                driver.refresh()
            except Exception as e:
                print(f"Failed to load cookies: {e}")
                os.remove(COOKIES_PATH)
                print("Deleted corrupted cookies file. Will perform a fresh login.")

        if not cookies_loaded:
            print("Navigating to CollegeScheduler login page...")
            driver.get("https://tamu.collegescheduler.com")

        global term_td
        term_td = None
        try:
            change_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//a[contains(@class, 'btnLinkCss') and contains(text(), 'Change')]")))
            print("Already logged in, skipping login steps. (1)")
        except:
            try:
                term_td = wait.until(EC.element_to_be_clickable((By.XPATH, "//td[contains(text(), 'Spring 2025 - Galveston')]"))) or None
                print("Already logged in, skipping login steps. (2)")
            except:
                print("Logging in...")
                wait = WebDriverWait(driver, 30)
                email_input = wait.until(EC.presence_of_element_located((By.NAME, "loginfmt")))
                email_input.send_keys(USERNAME)
                email_input.send_keys(Keys.RETURN)

                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                print("Page is fully loaded after entering email.")

                time.sleep(3)

                password_input = wait.until(EC.presence_of_element_located((By.NAME, "passwd")))
                password_input.send_keys(PASSWORD)
                password_input.send_keys(Keys.RETURN)

                print("pass")

                try:
                    yes_device_button = wait.until(EC.element_to_be_clickable((By.ID, "trust-browser-button")))
                    driver.execute_script("arguments[0].click();", yes_device_button)
                    print("Clicked 'Yes, this is my device' button.")
                except:
                    notify_discord(f"Duo login failed, waiting for you to restart app and be there to login (so duo account isnt disabled)")
                    time.sleep(999999999)

                try:
                    stay_signed_in_button = wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9")))
                    stay_signed_in_button.click()
                    print("Clicked 'Stay signed in?' button.")
                except:
                    print("No 'Stay signed in?' prompt appeared.")
                    
                with open(COOKIES_PATH, "wb") as cookies_file:
                    pickle.dump(driver.get_cookies(), cookies_file)
                    print("Cookies saved for future sessions.")
        
        # Selecting the term and checking seat availability
        try:
            if term_td is None:
                current_term = driver.find_element(By.XPATH, "//div[contains(text(), 'Fall 2024 - College Station')]")
                if current_term:
                    print("Changing term to Spring 2025 - Galveston...")
                    change_button = driver.find_element(By.XPATH, "//a[contains(text(), 'Change') and @href='/terms/Fall 2024 - College Station']")
                    driver.execute_script("arguments[0].click();", change_button)
        except Exception as e:
            print(f"An error occurred while changing the term: {e}")
        
        try:
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
            print("Page is fully loaded before selecting term.")

            term_td = wait.until(EC.element_to_be_clickable((By.XPATH, "//td[contains(text(), 'Spring 2025 - Galveston')]")))
            driver.execute_script("arguments[0].click();", term_td)

            save_continue_button = wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[.//span[contains(text(), 'Save')] or contains(text(), 'Save and Continue')]")
            ))
            driver.execute_script("arguments[0].click();", save_continue_button)

            print(f"Button '{save_continue_button.text}' clicked.")
        except Exception as e:
            print(f"An error occurred while selecting the term: {e}")

        # Navigating to sections and checking seat availability
        for CLASS_NAME in CLASS_NAMES:
            try:
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                print("Page is fully loaded before clicking 'Sections'.")

                sections_link = wait.until(EC.element_to_be_clickable(
                    (By.XPATH, f"//a[contains(@aria-label, 'Sections for') and contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{CLASS_NAME}')]")
                ))

                driver.execute_script("arguments[0].click();", sections_link)
                print(f"Clicked 'Sections' link for class matching '{CLASS_NAME}'.")
            except Exception as e:
                print(f"An error occurred while clicking the 'Sections' link: {e}")

            clr_session = False

            # Checking seat availability
            try:
                time.sleep(3)
                wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
                print("Page is fully loaded before checking seat availability.")

                rows = driver.find_elements(By.XPATH, "//tbody[@class='css-1c24da2-groupCss' or @class='css-49bt64-groupCss-darkGroupCss-altCss']//tr")
                for row in rows:
                    try:
                        section_details = row.find_elements(By.TAG_NAME, "td")
                        if len(section_details) > 7:
                            print(section_details[2].text.strip())
                            crn = section_details[2].text.strip()
                            seats_open = section_details[7].text.strip()
                            if int(seats_open) > 0:
                                print(seats_open)
                                notify_discord(f"New opening: CRN {crn} under your entry '{CLASS_NAME}' has {seats_open} seats open now!")
                    except Exception as e:
                        print(f"Error processing row: {e}")
                        continue
            except Exception as e:
                print(f"An error occurred while checking seat availability: {e}")
            try:
                back_button= wait.until(EC.element_to_be_clickable(
                    (By.XPATH, "//button[.//span[contains(text(), 'Save')] or contains(text(), 'Save and Continue')]")
                ))
                driver.execute_script("arguments[0].click();", back_button)
            except:
                print(f"Error trying to to back: {e}")


    finally:
        done = True
        driver.quit()
        print("Done!")

def start_monitoring():
    global done
    with concurrent.futures.ThreadPoolExecutor() as executor:
        while True:
            executor.submit(login_collegescheduler)
            print("Submitted a new task to check for seat availability.")
            while not done:
                time.sleep(5)
            done = False


if __name__ == "__main__":
    start_monitoring()
