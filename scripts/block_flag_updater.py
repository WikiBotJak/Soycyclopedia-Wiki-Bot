import pywikibot
import re
import ipaddress
import mwparserfromhell

TEMPLATE_NAMES = ["{{Permablocked}}", "{{Permabanned}}"]
SUMMARY_ADD = "Add {{Permablocked}} to permanently blocked user"
SUMMARY_REMOVE = "Remove {{Permablocked}} from unblocked user"

def is_ip_address(value):
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False

def update_block_flags(site):
    print("[*] Checking recent block log events...")

    for event in site.logevents('block', total=5):
        username = event.page().title(with_ns=False)

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

        print(f"[*] {username} → Blocked: {is_blocked}, Perm: {is_perm_block}")

        # Get current content
        if user_page.exists():
            text = user_page.text
        else:
            text = ""

        has_template = any(t.lower() in text.lower() for t in TEMPLATE_NAMES)

        if is_perm_block and not has_template:
            # Add the {{Pemablocked}} template to top
            print(f"[+] Adding Pemablocked to {username}")
            new_text = f"{{{{Permablocked}}}}\n{text}"
            user_page.text = new_text
            user_page.save(summary=SUMMARY_ADD)

        elif not is_perm_block and has_template:
            print(f"[-] Removing Permablocked/Permabanned from {username}")
            code = mwparserfromhell.parse(text)
            for tpl in code.filter_templates():
                name = tpl.name.strip().lower()
                if name in ("permablocked", "permabanned"):
                    code.remove(tpl)

            new_text = str(code).lstrip('\n')
            if new_text != text:
                user_page.text = new_text
                user_page.save(summary=SUMMARY_REMOVE)
