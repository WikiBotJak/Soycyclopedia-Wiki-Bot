import pywikibot
from datetime import datetime, timedelta, timezone

# --- CONFIG ---
EDIT_WAR_THRESHOLD = 4 # Number of back-and-forth edits before triggering
LOCK_EXPIRY = "3 day"  # Temporary protection duration
PROTECTION_LEVEL = "sysop"
CONTROVERSIAL_TEMPLATE = "{{Controversial}}"
ADMIN_USERNAME = "Cobblestone"  # Who to ping on the talk page after detecting an edit war
MAX_TIME_WINDOW = timedelta(minutes=90) # max amount of time to check
SIMILAR_DELTA = 20  # bytes within which additions/removals are considered "similar"
MAX_USERS = 3 # Max distinct users involved for it to count as an edit war

def detect_edit_war(site, page_title):
    page = pywikibot.Page(site, page_title)
    endtime = datetime.utcnow()
    starttime = endtime - MAX_TIME_WINDOW

    protections = page.protection()
    edit_level = protections.get('edit')
    if edit_level == 'sysop':
        print(f"[x] Skipping {page_title} (already sysop protected)")
        return False

    try:
        revisions = list(page.revisions(starttime=starttime, endtime=endtime, content=False, reverse=True))
    except pywikibot.exceptions.NoPageError:
        return False
    except pywikibot.exceptions.IsRedirectPageError:
        return False

    print(f"[*] {len(revisions)} revisions checked on {page_title}")
    if len(revisions) < EDIT_WAR_THRESHOLD * 2:
        return False  # Not enough revisions to judge

    size_diffs = []
    users = []
    prev_size = revisions[0].size

    for rev in revisions[1:]:
        diff = rev.size - prev_size
        size_diffs.append(diff)
        users.append(rev.user)
        prev_size = rev.size

    # Count "direction changes" in byte deltas (add/remove alternation)
    similar_count = 0
    for i in range(1, len(size_diffs)):
        if abs(abs(size_diffs[i]) - abs(size_diffs[i - 1])) <= SIMILAR_DELTA and users[i] != users[i - 1]:
            similar_count += 1


    if len(set(users)) > MAX_USERS:
        return False

    print(f"[+] {page_title}: {similar_count} similar back-and-forth edits")
    return similar_count >= EDIT_WAR_THRESHOLD


def lock_page_and_notify(site, page_title):
    page = pywikibot.Page(site, page_title)
    talk_page = page.toggleTalkPage()

    # Protect the page
    print(f"Locking {page.title()} for {LOCK_EXPIRY} due to edit warring.")
    page.protect(protections={'edit': PROTECTION_LEVEL},
                 reason="Edit war detected. Page temporarily protected",
                 expiry=LOCK_EXPIRY)

    # Add controversial template if not already present
    text = page.get()
    if CONTROVERSIAL_TEMPLATE not in text:
        page.text = CONTROVERSIAL_TEMPLATE + "\n" + text
        page.save(summary="Marking page as controversial due to edit war")

    # Notify on talk page
    notification = (
        f"== Edit war detected ==\n"
        f"'''Automated Notice:''' The page [[{page.title()}]] was automatically protected for {LOCK_EXPIRY} "
        f"due to repeated edit warring.\n\n"
        f"[[User:{ADMIN_USERNAME}]] and other jannies, please review the situation and consider manual resolution.\n"
        f"-- ~~~~"
    )
    talk_text = talk_page.get() if talk_page.exists() else ""
    talk_page.text = talk_text + "\n\n" + notification
    talk_page.save(summary="Notifying jannies of edit war and protection")

def check_edit_wars(site):
    """Check recent changes for pages in edit wars and take action if needed."""
    print("[*] Checking for edit wars...")
    recent_changes = list(site.recentchanges(total=15))

    seen_pages = set()
    for change in recent_changes:
        title = change['title']
        if title in seen_pages:
            continue
        seen_pages.add(title)

        if detect_edit_war(site, title):
            lock_page_and_notify(site, title)
    return recent_changes