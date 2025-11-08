import pywikibot
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from scripts.infoboxUpdater import InfoboxUpdater
from scripts.updateNewesetArticles import update_newest_articles
from scripts.block_flag_updater import update_block_flags
from scripts.archiveis_archiver import MementoArchiver
from scripts.fix_double_redirects import check_redirects
from scripts.edit_warring_detector import check_edit_wars

def login_bot():
    site = pywikibot.Site()
    if not site.logged_in():
        site.login()
    print(f"Logged in as: {site.user()}")
    return site

def update_infoboxes_and_multi_redirects():
    site = login_bot()
    updater = InfoboxUpdater(site)
    updater.run()
    check_redirects(site)

def update_na():
    site = login_bot()
    update_newest_articles(site)

def update_blocks_and_archives():
    site = login_bot()
    update_block_flags(site)
    preloaded_recent_changes = check_edit_wars(site)
    #archiver = MementoArchiver(site, preloaded_recent_changes)
    #archiver.run_recentchanges()


def main():
    scheduler = BlockingScheduler() #BlockingScheduler keeps the script running

    scheduler.add_job(
        update_blocks_and_archives,
        trigger=CronTrigger(hour='*/1'),
        name="Block Flag And Archiver Sync",
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
        update_infoboxes_and_multi_redirects,
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
