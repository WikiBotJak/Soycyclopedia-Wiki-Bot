import os

import pywikibot
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from pywikibot.login import BotPassword

from scripts.infoboxUpdater import InfoboxUpdater
from scripts.updateNewesetArticles import update_newest_articles
from scripts.block_flag_updater import update_block_flags
from scripts.archiveis_archiver import MementoArchiver
from scripts.fix_double_redirects import check_redirects
from scripts.edit_warring_detector import check_edit_wars

BOT_USERNAME = "SoycyclopediaBot"

def login_bot():
    """Create a new Site object and log in with bot password."""
    site = pywikibot.Site()
    bot_password = os.environ.get("WIKI_PASS")
    if not bot_password:
        raise RuntimeError("WIKI_PASS environment variable not set!")
    site.login(BotPassword(BOT_USERNAME, bot_password))
    print(f"Logged in as: {site.user()}")
    return site


def ensure_login(site):
    if not site.logged_in():
        print("[*] Session expired, logging in again...")
        site.login()

def update_infoboxes_and_multi_redirects(site):
    ensure_login(site)
    updater = InfoboxUpdater(site)
    updater.run()
    check_redirects(site)

def update_na(site):
    ensure_login(site)
    update_newest_articles(site)

def update_blocks_and_archives(site):
    ensure_login(site)
    update_block_flags(site)
    # preloaded_recent_changes = check_edit_wars(site)
    # archiver = MementoArchiver(site, preloaded_recent_changes)
    # archiver.run_recentchanges()

def main():
    scheduler = BlockingScheduler()
    site = login_bot()

    # Hourly job
    scheduler.add_job(
        lambda: update_blocks_and_archives(site),
        trigger=CronTrigger(hour="*/1"),
        name="Block Flag And Archiver Sync"
    )

    # Daily job
    scheduler.add_job(
        lambda: update_na(site),
        trigger=CronTrigger(hour=0, minute=0),
        name="Daily Main Page Article Update"
    )

    # Weekly job
    scheduler.add_job(
        lambda: update_infoboxes_and_multi_redirects(site),
        trigger=CronTrigger(day_of_week="fri"),
        name="Weekly Infobox Update"
    )

    try:
        print("[*] Starting scheduler...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[x] Scheduler shutting down...")

# entry point
if __name__ == '__main__':
    main()
