import time

import pywikibot
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from infoboxUpdater import  InfoboxUpdater

def update_infoboxes():
    site = pywikibot.Site()
    if not site.logged_in():
        site.login()
    print(f"Logged in as: {site.user()}")
    # run task 1 - Update post count for infobox soyjak templates
    updater = InfoboxUpdater(site)
    updater.run()


def main():
    scheduler = BlockingScheduler() #BlockingScheduler keeps the script running

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