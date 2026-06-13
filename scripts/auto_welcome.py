from datetime import timedelta

import pywikibot

def welcome_user(user: pywikibot.User):
    talk_page = user.getUserTalkPage()
    welcome_text = f"{{{{subst:Welcome}}}}"

    try:
        if talk_page.exists():
            print(f"[i] Skipping {user.username}: already welcomed")
            return
        else:
            talk_page.text = welcome_text + "\n"

            talk_page.save(
                summary=f"Welcoming new user",
                minor=False
            )

        print(f"[✅] Welcomed {user.username}")
    except Exception as e:
        print(f"[x] Could not welcome {user.username}: {e}")


def should_skip_page(user) -> bool:
    if user.is_blocked():
        return True
    elif 'bot' in user.groups():
        return True
    elif user.username.startswith("~"):
        return True
    elif user.editCount() < 1:
        return True
    else:
        return False

def check_new_users(site, days_back=12, limit=100):
    print("[*] Welcoming new users")

    start = site.server_time() - timedelta(days=days_back)
    logs = site.logevents(logtype="newusers", end=start, total=limit)


    for log in logs:
        if log.action() not in ("create", "autocreate"):
            continue

        try:
            user = log.page()

            if not should_skip_page(user):
                welcome_user(user)
            else:
                print(f"[i] Skipping {user.username}: has not edited before")

        except Exception as e:
            print(f"[x] Error processing user: {e}")
