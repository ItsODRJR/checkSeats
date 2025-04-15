# 📅 CheckSeats
An Automated CollegeScheduler Monitor & Class Swapper for Texas A&M University

This is a desktop utility that monitors Texas A&M University’s **College Scheduler** and **automatically alerts or swaps courses** based on your configuration. Perfect for grabbing those hard-to-get class slots before anyone else does.

---

## 🔧 Features

- ✅ Monitors open seats for selected classes
- 🔁 Automatically swaps from one section to another
- 🔔 Sends you real-time Discord alerts when changes happen
- 🛠 Configurable UI for easy setup (just run the `.exe`)

---

## 📥 Setup & Usage Guide

### 1. **Download and Run**

Just download the `ClassCheck.exe` file and double-click it. No installation required.

---

### 2. **Fill in the Required Settings**

In the config screen:

- **CollegeScheduler Username** – Your TAMU email
- **CollegeScheduler Password** – Your TAMU login password
- **CollegeScheduler Cookie** – Your auth cookie (grab on https://tamu.collegescheduler.com/ via browser dev tools or use a session generator)
- **Discord Token** – Your Discord bot token (https://discord.com/developers/applications)
- **Discord Channel Name** – The name of the Discord channel to send alerts to (e.g., `general`)
- **Discord Account ID** – Your full Discord user ID (activate developer mode, right click your profile and click copy ID
- **Term Name** – Choose the desired term (e.g., `Fall 2025 - College Station`)

---

### 3. **Select Mode**

Choose one of the two options:

- 🔍 **Watch Mode** – Get notified when a class becomes available.
- 🔄 **Swap Mode** – Automatically attempts to swap from one section to another.

If using **Swap Mode**:
- **Swap From**: Enter the CRN you are currently enrolled in.
- **Swap To**: Enter the CRN you want to switch into.

---

### 4. **Add Courses to Watch**

- In the dropdown, search for the course (e.g., `CSCE`, `ACCT`, etc.)
- Click **Add Course** for each class you want to track
- Click **Save Config**

---

## 📡 How It Works

The app logs into TAMU College Scheduler using your credentials and cookie, continuously checks for course availability, and posts to your Discord when it detects changes or performs swaps. Make sure to keep the app running while monitoring.

---

## 🛠 Requirements

- Windows 10+
- Discord bot token + channel setup
- Valid TAMU Net ID login and session cookie

---

## ❗Disclaimer

This tool is unofficial and not affiliated with Texas A&M University. Use at your own discretion and always comply with your institution’s academic policies.
