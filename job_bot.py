import os
import asyncio
import logging
import json
from dotenv import load_dotenv
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import Bot
import httpx

# ------------------ Logging setup ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("job_bot")

# ------------------ Load environment variables ------------------
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

bot = Bot(token=BOT_TOKEN)

# ------------------ Persist sent jobs ------------------
SENT_JOBS_FILE = "sent_jobs.json"
try:
    with open(SENT_JOBS_FILE, "r") as f:
        sent_jobs = set(json.load(f))
except FileNotFoundError:
    sent_jobs = set()

# ------------------ Google Jobs via SerpAPI ------------------
async def fetch_google_jobs(query="IT jobs in India"):
    logger.info(f"Fetching Google Jobs via SerpAPI for query='{query}'")
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "google_jobs",
        "q": query,
        "hl": "en",
        "api_key": SERPAPI_KEY,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        if resp.status_code != 200:
            logger.error(f"SerpAPI request failed: {resp.status_code} {resp.text}")
            return []

        data = resp.json()

    jobs = []
    for job in data.get("jobs_results", []):
        title = job.get("title", "N/A")
        company = job.get("company_name", "N/A")
        location = job.get("location", "N/A")
        posted = job.get("detected_extensions", {}).get("posted_at", "N/A")

        # Collect all apply links
        links = [link.get("link") for link in job.get("related_links", []) if "link" in link]
        apply_links = "\n".join([f"🔗 [Apply Here]({l})" for l in links]) if links else "No link available"

        jobs.append(
            {
                "id": f"{title}_{company}_{location}",  # unique ID
                "text": f"📌 *{title}*\n🏢 {company}\n📍 {location}\n🕒 {posted}\n{apply_links}"
            }
        )

    logger.info(f"Google Jobs: found {len(jobs)} jobs")
    return jobs

# ------------------ Telegram Sender ------------------
async def send_to_telegram(jobs):
    for job in jobs:
        try:
            await bot.send_message(
                chat_id=CHAT_ID,
                text=job["text"],
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

# ------------------ Task ------------------
async def job_task():
    global sent_jobs
    logger.info("Checking for new jobs...")
    google_jobs = await fetch_google_jobs()

    new_jobs = []
    for job in google_jobs:
        if job["id"] not in sent_jobs:
            new_jobs.append(job)
            sent_jobs.add(job["id"])

    if new_jobs:
        logger.info(f"Sending {len(new_jobs)} new jobs to Telegram...")
        await send_to_telegram(new_jobs)
        # Persist sent jobs
        with open(SENT_JOBS_FILE, "w") as f:
            json.dump(list(sent_jobs), f)
    else:
        logger.info("No new jobs found.")

# ------------------ Scheduler ------------------
async def main():
    scheduler = AsyncIOScheduler()
    # Check every 15 minutes
    scheduler.add_job(job_task, "interval", minutes=15)
    scheduler.start()

    logger.info("Scheduler started. Running first job immediately...")
    await job_task()

    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
