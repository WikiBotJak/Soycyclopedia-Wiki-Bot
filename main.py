from datetime import datetime, timedelta, timezone

import pywikibot
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from Services.ru_account_service import SoybooruAuth
from scripts.auto_welcome import check_new_users
from scripts.community_dailyjak import create_community_dailyjak
from scripts.dailyjak import run_dailyjak
from scripts.featured_gem import update_featured_gem
from scripts.infoboxUpdater import InfoboxUpdater
from scripts.tag_last_posts import tag_last_posts
from scripts.updateNewesetArticles import update_newest_articles
#from scripts.block_flag_updater import update_block_flags
from scripts.archiveis_archiver import MementoArchiver
from scripts.fix_double_redirects import check_redirects
from scripts.edit_warring_detector import check_edit_wars
from scripts.redirect_new_snca_pages import scan_snca_pages
from scripts.sandbox_reset import reset_sandbox

def get_site():
    site = pywikibot.Site()
    site.login()
    return site

def is_wiki_blocked(site):
    data = site.simple_request(
        action="query",
        meta="userinfo",
        uiprop="blockinfo"
    ).submit()

    userinfo = data.get("query", {}).get("userinfo", {})
    return "blockedby" in userinfo


def is_ru_banned(auth):
    res = auth.get(f"https://soybooru.com/api/User/{auth.username}")

    data = res.json()
    return bool(data.get("activeBans") or data.get("activeBanZones"))

def get_ru_auth_if_allowed(auth):
    if is_ru_banned(auth):
        print("[x] SoyBooru bot is banned. Skipping SoyBooru tasks.")
        return None

    return auth


def get_site_if_allowed():
    site = get_site()

    if is_wiki_blocked(site):
        print("[x] Wiki bot is banned. Skipping wiki tasks.")
        return None

    return site

def update_na():
    site = get_site_if_allowed()

    if not site:
        return

    update_featured_gem(site)
    update_newest_articles(site)
    check_new_users(site)


def daily_sandbox_reset():
    site = get_site_if_allowed()

    if not site:
        return

    reset_sandbox(site)


def update_blocks_and_archives(auth):
    site = get_site_if_allowed()

    # if site:
    #     update_block_flags(site)

    if get_ru_auth_if_allowed(auth):
        tag_last_posts(auth)

def update_community_dailyjak(auth):
    site = get_site_if_allowed()
    if not site:
        return

    if get_ru_auth_if_allowed(auth):
        # create_community_dailyjak(site, auth)
        updater = InfoboxUpdater(site, auth)
        updater.run()

    check_redirects(site)
    #scan_snca_pages(site)


def update_dailyjak(scheduler, auth, attempt=1, max_attempts=24):
    site = get_site_if_allowed()
    if not site:
        return

    if not get_ru_auth_if_allowed(auth):
        return

    try:
        run_dailyjak(site, auth)
    except Exception as e:
        print(f"[!] Dailyjak update failed (attempt {attempt}/{max_attempts}): {e}")
        if attempt < max_attempts:
            retry_time = datetime.now(timezone.utc) + timedelta(hours=1)
            scheduler.add_job(
                update_dailyjak,
                trigger="date",
                run_date=retry_time,
                args=[scheduler, auth, attempt + 1, max_attempts],
                name=f"Dailyjak Retry #{attempt + 1}",
                misfire_grace_time=3600,
            )
            print(f"[*] Scheduled retry #{attempt + 1} at {retry_time.isoformat()}")
        else:
            print(f"[x] Dailyjak update failed after {max_attempts} attempts, giving up until next day")


def main():
    scheduler = BlockingScheduler()
    auth = SoybooruAuth()

    scheduler.add_job(
        update_dailyjak,
        trigger=CronTrigger(hour=0, minute=5),
        args=[scheduler, auth],
        name="Daily Dailyjak Update",
        coalesce=True,
        misfire_grace_time=3600
    )
    scheduler.add_job(
        update_community_dailyjak,
        trigger=CronTrigger(day_of_week="sun", hour=0, minute=1),
        args=[auth],
        name="Weekly Community Dailyjak",
        coalesce=True,
        misfire_grace_time=3600
    )

    scheduler.add_job(
        update_blocks_and_archives,
        trigger=CronTrigger(hour="*/2"),
        args=[auth],
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
        daily_sandbox_reset,
        trigger=CronTrigger(hour=0, minute=0),
        name="Daily Sandbox Reset",
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
