import pywikibot
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from scripts.infoboxUpdater import InfoboxUpdater
from scripts.updateNewesetArticles import update_newest_articles
from scripts.block_flag_updater import update_block_flags
from scripts.archiveis_archiver import MementoArchiver
from scripts.fix_double_redirects import check_redirects
from scripts.edit_warring_detector import check_edit_wars
from scripts.redirect_new_snca_pages import scan_snca_pages

def get_site():
    site = pywikibot.Site()
    return site

def update_infoboxes_and_multi_redirects():
    site = get_site()
    updater = InfoboxUpdater(site)
    updater.run()
    check_redirects(site)
    scan_snca_pages(site)


def update_na():
    site = get_site()
    update_newest_articles(site)


def update_blocks_and_archives():
    site = get_site()
    update_block_flags(site)

    # preloaded_recent_changes = check_edit_wars(site)
    # archiver = MementoArchiver(site, preloaded_recent_changes)
    # archiver.run_recentchanges()

def main():
    scheduler = BlockingScheduler()
    
    scheduler.add_job(
        update_blocks_and_archives,
        trigger=CronTrigger(hour="*/1"),
        name="Block Flag And Archiver Sync",
        coalesce=True,
        misfire_grace_time=3600
    )

    scheduler.add_job(
        update_na,
        trigger=CronTrigger(hour=0, minute=0),
        name="Daily Main Page Article Update",
        coalesce=True,
        misfire_grace_time=3600 
    )

    scheduler.add_job(
        update_infoboxes_and_multi_redirects,
        trigger=CronTrigger(day_of_week="fri"),
        name="Weekly Infobox Update",
        coalesce=True,
        misfire_grace_time=3600 
    )

    try:
        print("[*] Starting scheduler...")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[x] Scheduler shutting down...")

# entry point
if __name__ == '__main__':
    main()
