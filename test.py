import os
import json
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# Configuration file paths
CONFIG_DIR = os.path.join(os.environ["LOCALAPPDATA"], "TAMUClassSwap")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

def load_config():
    if not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump({}, f, indent=4)
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)

def save_config(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=4)

def refresh_cookie_selenium(username, password, headless=True):
    """
    Uses Selenium to login to CollegeScheduler via Microsoft SSO,
    extracts and returns the cookie as a string, then quits the browser.
    
    Adjust the URLs, element locators, and wait conditions as needed.
    """
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
    options.add_argument("--start-maximized")
    # Optional: mimic common browser headers (some sites may require this)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
    
    # Create a new Chrome session.
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    wait = WebDriverWait(driver, 10)
    
    try:
        # Step 1: Navigate to the CollegeScheduler entry page.
        # (This should redirect you to the SSO login page)
        entry_url = "https://tamu.collegescheduler.com/entry"
        driver.get(entry_url)

        # Step 2: Check if login is required. For example, if an element with name "loginfmt" is present.
        try:
            email_input = wait.until(EC.presence_of_element_located((By.NAME, "loginfmt")))
        except Exception:
            # If the login input is not found, you might already be logged in.
            print("Login page did not load as expected; assuming already logged in.")
        else:
            # Fill in your username and submit.
            email_input.clear()
            email_input.send_keys(username)
            email_input.send_keys(Keys.RETURN)
            # Wait a moment for transition.
            wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
            time.sleep(3)

            # Step 3: Find the password input and enter your password.
            password_input = wait.until(EC.presence_of_element_located((By.NAME, "passwd")))
            password_input.clear()
            password_input.send_keys(password)
            password_input.send_keys(Keys.RETURN)

            try:
                yes_device_button = wait.until(EC.element_to_be_clickable((By.ID, "trust-browser-button")))
                driver.execute_script("arguments[0].click();", yes_device_button)
            except:
                #notify_discord("Duo login failed. Manual intervention required. " + DC_PING_NAME)
                time.sleep(99999999)

            # Optionally, handle “Stay signed in?” or “Trust this device” if they appear.
            try:
                stay_signed_in = wait.until(EC.element_to_be_clickable((By.ID, "idSIButton9")))
                stay_signed_in.click()
            except Exception as e:
                print("Stay signed in prompt not found or already handled:", e)

        # Step 4: Wait for a page element that signals successful login.
        # For example, wait until a logout link or some indicator appears.
        # Adjust the locator according to your application.
        wait.until(EC.element_to_be_clickable((By.XPATH, f"//td[contains(text(), 'Fall 2025 - College Station')]")))
        
        # (Optional) Navigate to a dashboard URL to ensure the CollegeScheduler cookie is set.
        dashboard_url = "https://tamu.collegescheduler.com/dashboard"
        driver.get(dashboard_url)
        wait.until(lambda d: d.execute_script("return document.readyState") == "complete")
        
        # Step 5: Extract cookies from the browser session.
        cookies = driver.get_cookies()
        print(cookies)
        if cookies:
            cookie_str = "; ".join([f"{cookie['name']}={cookie['value']}" for cookie in cookies])
            # Save new cookie to config file.
            config_data = load_config()
            config_data["cookie"] = cookie_str
            save_config(config_data)
            print("Cookie refreshed successfully!")
            return cookie_str
        else:
            print("No cookies found after login.")
            return None
    except Exception as e:
        print("Error during Selenium login:", e)
        return None
    finally:
        driver.quit()


# Example usage:
if __name__ == "__main__":
    config = load_config()
    username = config.get("username", "your_username")
    password = config.get("password", "your_password")
    new_cookie = refresh_cookie_selenium(username, password, headless=True)
    print("New Cookie:", new_cookie)
