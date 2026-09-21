import os
import re
import tempfile
from datetime import datetime, timedelta, timezone

import pywikibot

from Services.ru_account_service import SoybooruAuth

DAILYJAK_URL = "https://soybooru.com/api/booru/dailyjak"
BOORU_POSTS_URL = "https://soybooru.com/api/booru/posts"
BOORU_POST_VIEW = "https://soybooru.com/post/view"

MIME_TO_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}


def fetch_dailyjak_id(auth):
    """Fetch the dailyjak endpoint and extract the post ID from the redirect."""
    print("[*] Fetching dailyjak post ID...")

    res = auth.get(DAILYJAK_URL, allow_redirects=False)

    location = res.headers.get("Location", "")
    if location:
        match = re.search(r"/posts/(\d+)/file", location)
        if match:
            post_id = int(match.group(1))
            print(f"[*] Dailyjak post ID (from redirect): {post_id}")
            return post_id

    res = auth.get(DAILYJAK_URL, stream=True)
    try:
        match = re.search(r"/posts/(\d+)/file", res.url)
        if match:
            post_id = int(match.group(1))
            print(f"[*] Dailyjak post ID (from final URL): {post_id}")
            return post_id
    finally:
        res.close()

    raise RuntimeError(
        f"Could not extract post ID from dailyjak endpoint. "
        f"Location: {location!r}, Final URL: {res.url!r}"
    )


def get_extension_from_response(res):
    """Determine file extension from response Content-Type header."""
    content_type = res.headers.get("Content-Type", "").split(";")[0].strip().lower()
    return MIME_TO_EXT.get(content_type, ".png")


def download_dailyjak_image(auth, post_id):
    """Download the dailyjak image file and return (local_path, extension)."""
    url = f"{BOORU_POSTS_URL}/{post_id}/file"

    print(f"[*] Downloading dailyjak image (post #{post_id})...")

    with auth.get(url, stream=True) as res:
        ext = get_extension_from_response(res)
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)

        for chunk in res.iter_content(chunk_size=1024 * 1024):
            if chunk:
                tmp.write(chunk)

        tmp.close()

    print(f"[*] Downloaded to {tmp.name}")
    return tmp.name, ext


def upload_to_wiki(site, local_path, wiki_filename, post_id):
    """Upload the dailyjak image to the wiki."""
    file_page = pywikibot.FilePage(site, f"File:{wiki_filename}")

    if file_page.exists():
        print(f"[*] File already exists: File:{wiki_filename}")
        return file_page

    comment = "Uploading Dailyjak"
    text = f"==Licensing==\n{{{{Booru|1={post_id}}}}}"

    file_page.upload(
        source=local_path,
        comment=comment,
        text=text,
        ignore_warnings=True,
    )

    print(f"[+] Uploaded File:{wiki_filename}")
    return file_page


def update_user_page(site, page_title, wiki_filename, post_id):
    """Create or replace a User:Gem page with the dailyjak image."""
    page = pywikibot.Page(site, page_title)
    content = f"[[File:{wiki_filename}|link={BOORU_POST_VIEW}/{post_id}]]"

    if page.exists() and page.text.strip() == content.strip():
        print(f"[-] Page already up to date: {page_title}")
        return

    page.text = content
    page.save(summary=f"Updating Dailyjak (post #{post_id})")
    print(f"[+] Updated {page_title}")


def run_dailyjak(site, auth):
    """Main dailyjak workflow: fetch → download → upload → update pages."""
    now = datetime.now(timezone.utc)
    today = now.date()
    tomorrow = today + timedelta(days=1)

    today_dd_mm_yyyy = today.strftime("%d-%m-%Y")

    today_page_title = f"Dailyjak:{today.strftime('%B')} {today.day}, {today.year}"
    tomorrow_page_title = f"Dailyjak:{tomorrow.strftime('%B')} {tomorrow.day}, {tomorrow.year}"

    print(f"[*] Running dailyjak for {today.isoformat()}")
    print(f"[*] Today page:    {today_page_title}")
    print(f"[*] Tomorrow page: {tomorrow_page_title}")

    post_id = fetch_dailyjak_id(auth)

    local_path, ext = download_dailyjak_image(auth, post_id)

    try:
        wiki_filename = f"Dailyjak {today_dd_mm_yyyy}{ext}"
        upload_to_wiki(site, local_path, wiki_filename, post_id)

        update_user_page(site, today_page_title, wiki_filename, post_id)
        update_user_page(site, tomorrow_page_title, wiki_filename, post_id)

        print(f"[✓] Dailyjak update complete for {today.isoformat()}")
    finally:
        if local_path and os.path.exists(local_path):
            os.remove(local_path)
