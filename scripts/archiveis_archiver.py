import re
import requests
import pywikibot
import os

LINK_RE = re.compile(r'(?<![=/?])https?://(?:www\.)?soyjak\.st/[^\s\]\|<>]+')
NOARCHIVE_RE = re.compile(r'<!--\s*noarchive\s*-->', re.IGNORECASE)

class MementoArchiver:
    def __init__(self, site):
        self.site = site

    def get_latest_archive(self, url):
        """Query MementoWeb for an archive of this URL. Return snapshot URL or None."""
        timemap_url = f"http://archive.is/timemap/{url}"
        headers = {
            "User-Agent": os.environ['UA_AGENT']
        }
        try:
            # Fuck me, this api is vantablack coal. Why does it return results like this without json or xml? It is not even RESTful
            res = requests.get(timemap_url, headers=headers)
            if res.status_code != 200:
                return None
            for line in res.text.splitlines():
                if "memento" in line and "last" in line:
                    snapshot_url = line.split(";")[0].strip("<>")
                    return snapshot_url
        except Exception as e:
            print(f"[!] Error checking MementoWeb for {url}: {e}")
        return None

    def process_page(self, page):
        """Check a page for raw soyjak.st links, update with archives if available."""
        if page.namespace() != 0:
            return
        print(f"[*] Checking links of page {page.title()}")

        text = page.text
        changed = False

        for match in LINK_RE.finditer(text):
            link = match.group(0)

            # Skip if marked with <!--NOARCHIVE-->
            post_text = text[match.end():].lstrip()
            if NOARCHIVE_RE.match(post_text):
                print(f"    → Skipping {link} (marked NOARCHIVE)")
                continue

            print(f"[+] Found raw link: {link}")
            archive_url = self.get_latest_archive(link)

            if archive_url and archive_url not in text:
                # Replace raw link with archive
                print(f"    → Replacing with {archive_url}")
                text = text.replace(link, archive_url)
                changed = True
            elif not archive_url and "[needs archive]" not in text:
                # I would love to auto archive the imageboard links as needed, but for some niggalious reason, that is not supported, so we add a request for archive instead
                print(f"    → No archive found, marking")
                text = text.replace(link, f"{link} [needs archive]")
                changed = True

        if changed and text != page.text:
            page.text = text
            page.save(summary="Updating raw soyjak.st links for archive.ph")

    def run_recentchanges(self):
        print("[*] Checking recent pages to update archive links...")
        """Process the most recent changes."""
        seen_pages = set()

        for change in self.site.recentchanges(total=20):
            title = change["title"]
            if title in seen_pages:
                # skip duplicate entry for same page
                continue
            seen_pages.add(title)

            page = pywikibot.Page(self.site, title)
            self.process_page(page)
