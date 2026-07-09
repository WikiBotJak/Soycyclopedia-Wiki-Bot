import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import urlencode

import mwparserfromhell
import pywikibot

from Services.ru_account_service import SoybooruAuth

BOORU_API = "https://soybooru.com/api/booru/posts"
DAILYJAK_ARCHIVE_PAGE = "Main Page/The Dailyjak"

@dataclass
class DailyjakSlot:
    date_text: str
    date_obj: datetime
    template_index: int
    param_name: str | None
    line_index: int

def extension_from_post(post):
    original = post.get("originalFileName") or ""
    _, ext = os.path.splitext(original)
    return ext

def wiki_filename_for_post(post):
    ext = extension_from_post(post)
    return f"{post['id']} - soybooru{ext}"

def get_used_soybooru_ids(text):
    ids = set()

    pattern = re.compile(
        r"File:\s*(\d+)\s*-\s*soybooru(?:\.com)?",
        re.IGNORECASE
    )

    for match in pattern.finditer(text):
        ids.add(int(match.group(1)))

    return ids

def extract_soybooru_ids_from_text(text):
    ids = set()

    pattern = re.compile(
        r"File:\s*(\d+)\s*-\s*soybooru(?:\.com)?",
        re.IGNORECASE
    )

    for match in pattern.finditer(text):
        ids.add(int(match.group(1)))

    return ids


def find_next_available_slot(page_text):
    code = mwparserfromhell.parse(page_text)
    slots = []

    templates = code.filter_templates()
    for template_index, template in enumerate(templates):
        if not template.name.matches("Collapsegallery"):
            continue

        for param in template.params:
            value = str(param.value)
            if "File:Unknown.png" not in value:
                continue

            lines = value.splitlines()
            for line_index, line in enumerate(lines):
                if "File:Unknown.png" not in line:
                    continue

                match = re.search(r"\[\[Dailyjak:([^|\]]+)\|", line)

                if not match:
                    continue

                date_text = match.group(1).strip()

                try:
                    date_obj = datetime.strptime(date_text, "%B %d, %Y")
                except ValueError:
                    print(f"[!] Could not parse Dailyjak date: {date_text}")
                    continue

                slots.append(DailyjakSlot(
                    date_text=date_text,
                    date_obj=date_obj,
                    template_index=template_index,
                    param_name=str(param.name) if param.showkey else None,
                    line_index=line_index
                ))

    if not slots:
        return None

    future_slots = [
        slot for slot in slots
        if slot.date_obj.date() >= datetime.utcnow().date()
    ]

    usable_slots = future_slots or slots

    return sorted(usable_slots, key=lambda slot: slot.date_obj)[0]



def choose_unused_post(page_text, auth):
    today = datetime.utcnow().date()
    end_date = today - timedelta(days=7)
    start_date = end_date - timedelta(days=6)

    query = (
        f"order:score "
        f"date:{start_date.isoformat()}..{end_date.isoformat()}"
    )
    url = BOORU_API + "?" + urlencode({
        "page": 1,
        "pageSize": 5,
        "q": query
    })

    print(f"[*] Querying SoyBooru: {query}")

    res = auth.get(url)
    data = res.json()

    if not data["posts"]:
        print("[!] No SoyBooru posts found for scored week")
        return None, start_date, end_date

    posts = data.get("posts", [])
    used_ids = get_used_soybooru_ids(page_text)

    for post in posts:
        post_id = int(post["id"])

        if post.get("isTrashed"):
            print(f"[-] Skipping trashed post #{post_id}")
            continue

        if not post.get("isApproved", False):
            print(f"[-] Skipping unapproved post #{post_id}")
            continue

        if post_id in used_ids:
            print(f"[-] Skipping already-used post #{post_id}")
            continue

        return post, start_date, end_date

    print("[!] All checked top posts were already used or invalid")
    return None, start_date, end_date

def download_post_file(post, auth):
    post_id = post["id"]
    ext = extension_from_post(post)

    url = f"{BOORU_API}/{post_id}/file"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)

    print(f"[*] Downloading SoyBooru post #{post_id}")

    with auth.get(url, stream=True) as res:
        for chunk in res.iter_content(chunk_size=1024 * 1024):
            if chunk:
                tmp.write(chunk)

    tmp.close()
    return tmp.name

def upload_file_to_wiki(site, local_path, wiki_filename, post, start_date, end_date):
    file_page = pywikibot.FilePage(site, f"File:{wiki_filename}")

    if file_page.exists():
        print(f"[*] File already exists: File:{wiki_filename}")
        return file_page

    comment = f"Uploading Community Dailyjak from SoyBooru post #{post['id']}"
    description = f"Community Dailyjak: SoyBooru post #{post['id']} for {start_date.isoformat()}..{end_date.isoformat()}"

    file_page.upload(source=local_path, comment=comment, text=description, ignore_warnings=True)

    return file_page

def add_soyboor_comment_and_favorite(slot, post, auth):
    try:
        post_id = post["id"]

        urlComment = f"{BOORU_API}/{post_id}/comments"
        auth.post(urlComment, json={
            "content": f"[b][size=48px][color=#eab308]Dailyjakked: {slot.date_text}[/color][/size][/b]",
            "isAnonymous": False,
        })

        urlFavorite = f"{BOORU_API}/{post_id}/favorite"
        auth.post(urlFavorite)
        return True
    except Exception:
        return False


def create_dailyjak_page(site, slot, wiki_filename, post):
    title = f"Dailyjak:{slot.date_text}"
    page = pywikibot.Page(site, title)

    if page.exists():
        print(f"[*] Dailyjak page already exists: {title}")
        return

    page.text = f"[[File:{wiki_filename}]]"

    page.save(
        summary=f"Creating Community Dailyjak from SoyBooru post #{post['id']}"
    )

    print(f"[*] Created {title}")

def create_archive_page(new_archive_text, archive_text, archive_page, slot, post):
    if new_archive_text == archive_text:
        print("[!] Archive text did not change")
        return

    archive_page.text = new_archive_text
    archive_page.save(
        summary=(
            f"Adding Community Dailyjak for {slot.date_text} "
            f"from SoyBooru post #{post['id']}"
        )
    )

    print(
        f"[+] Added Community Dailyjak: "
        f"SoyBooru #{post['id']} -> {slot.date_text}"
    )

def replace_slot_in_archive(page_text, slot, wiki_filename):
    code = mwparserfromhell.parse(page_text)
    templates = code.filter_templates()

    template = templates[slot.template_index]

    for param in template.params:
        value = str(param.value)

        if 'File:Unknown.png' not in value:
            continue

        lines = value.splitlines()

        if slot.line_index >= len(lines):
            continue

        old_line = lines[slot.line_index]
        expected = f"[[Dailyjak:{slot.date_text}|{slot.date_text}]]"

        if "File:Unknown.png" not in old_line or expected not in old_line:
            continue

        lines[slot.line_index] = (
            f"File:{wiki_filename}|"
            f"[[Dailyjak:{slot.date_text}|{slot.date_text}]]"
        )
        param.value = "\n".join(lines)
        return str(code)
    return None



def create_community_dailyjak(site, auth):

    archive_page = pywikibot.Page(site, DAILYJAK_ARCHIVE_PAGE)
    archive_text = archive_page.text

    post, start_date, end_date = choose_unused_post(archive_text, auth)
    if not post:
        return

    slot = find_next_available_slot(archive_text)

    if not slot:
        print("[!] No available Unknown.png Dailyjak slots found")
        return

    wiki_filename = wiki_filename_for_post(post)
    local_path = None

    try:
        local_path = download_post_file(post, auth)

        upload_file_to_wiki(site, local_path, wiki_filename, post, start_date, end_date)
        create_dailyjak_page(site, slot, wiki_filename, post)
        new_archive_text = replace_slot_in_archive(archive_text, slot, wiki_filename)

        if new_archive_text:
            create_archive_page(new_archive_text, archive_text, archive_page, slot, post)
            add_soyboor_comment_and_favorite(slot, post, auth)
    finally:
        if local_path and os.path.exists(local_path):
            os.remove(local_path)

    return auth