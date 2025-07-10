import pywikibot
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from scripts.infoboxUpdater import InfoboxUpdater
from scripts.updateNewesetArticles import update_newest_articles
from scripts.block_flag_updater import update_block_flags

def login_bot():
    site = pywikibot.Site()
    if not site.logged_in():
        site.login()
    print(f"Logged in as: {site.user()}")
    return site

def update_infoboxes():
    site = login_bot()
    updater = InfoboxUpdater(site)
    updater.run()

def update_na():
    site = login_bot()
    updater = update_newest_articles(site)
    updater.run()

def update_blocks():
    site = login_bot()
    update_block_flags(site)


def main():
    scheduler = BlockingScheduler() #BlockingScheduler keeps the script running

    scheduler.add_job(
        update_na,
        trigger=CronTrigger(hour=2),
        name="Block Flag Sync",
        misfire_grace_time=3600  # if missed, run within an hour
    )

    # Run daily
    scheduler.add_job(
        update_na,
        trigger=CronTrigger(hour=0, minute=0),
        name="Daily Main Page Article Update",
        misfire_grace_time=3600 # if missed, run within an hour
    )

    # Run every Friday
    scheduler.add_job(
        update_infoboxes,
        trigger=CronTrigger(day_of_week='fri'),
        name="Weekly Infobox Update",
        misfire_grace_time=3600  # if missed, run within an hour
    )

    try:
        print("[*] Starting scheduler...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[x] Scheduler shutting down...")


if __name__ == '__main__':
    main()