import pywikibot
import re
import ipaddress
import mwparserfromhell

PERM_TEMPLATES = ["{{Permablocked}}", "{{Permabanned}}"]
TEMP_TEMPLATES = ["{{Banned}}", "{{Blocked}}"]

SUMMARY_ADD_PERM = "Add {{Permablocked}} to permanently blocked user"
SUMMARY_ADD_TEMP = "Add {{Blocked}} to temporarily blocked user"
SUMMARY_REMOVE = "Remove block templates from unblocked user"

def is_ip_address(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False

def update_block_flags(site):
    print("[*] Checking recent block log events...")

    seen_users = set()

    for event in site.logevents('block', total=5):
        username = event.page().title(with_ns=False)
        if username in seen_users:
            continue
        seen_users.add(username)

        #Skip temporary anon usernames
        if username.startswith('~'):
            print(f"[!] Skipping temp anon user: {username}")
            continue

        # Skip IP addresses
        if is_ip_address(username):
            print(f"[!] Skipping IP address: {username}")
            continue

        # Only handle User: pages
        user_page = pywikibot.Page(site, f"User:{username}")
        if user_page.namespace() != 2:
            continue

        # Check current block status
        block_info = list(site.blocks(users=[username]))
        is_blocked = bool(block_info)

        is_perm_block = is_blocked and block_info[0]['expiry'] == 'infinity'
        is_sitewide = is_blocked and 'sitewide' in event.params

        print(f"[*] {username} → Blocked: {is_blocked}, Perm: {is_perm_block}, Sitewide: {is_sitewide}")

        # Get current content
        if user_page.exists():
            text = user_page.text
        else:
            text = ""

        has_perm_template = any(
            t.lower() in text.lower()
            for t in PERM_TEMPLATES
        )

        has_temp_template = any(
            t.lower() in text.lower()
            for t in TEMP_TEMPLATES
        )

        if is_perm_block and is_sitewide and not has_perm_template:
            # Add the {{Permablocked}} template to top
            print(f"[+] Adding Permablocked to {username}")
            new_text = f"{{{{Permablocked}}}}\n{text}"
            user_page.text = new_text
            user_page.save(summary=SUMMARY_ADD_PERM)
        elif is_blocked and is_sitewide and not is_perm_block and not has_temp_template:
            # Add the {{Blocked}} template to top
            print(f"[+] Adding Blocked to {username}")

            new_text = f"{{{{Blocked}}}}\n{text}"
            user_page.text = new_text
            user_page.save(summary=SUMMARY_ADD_PERM)

        elif ((is_perm_block and is_sitewide and has_temp_template) or
        (is_blocked and is_sitewide and not is_perm_block and has_perm_template)):
            print(f"[-] Removing Permablocked/Blocked from {username}")
            code = mwparserfromhell.parse(text)
            for tpl in code.filter_templates():
                print(tpl)

                if (
                    tpl in PERM_TEMPLATES or
                    tpl in TEMP_TEMPLATES
                ):
                    code.remove(tpl)

            new_text = str(code).lstrip('\n')
            if new_text != text:
                user_page.text = new_text
                user_page.save(summary=SUMMARY_REMOVE)
