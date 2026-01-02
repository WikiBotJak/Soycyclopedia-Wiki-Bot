import pywikibot
import mwparserfromhell
import requests
from datetime import datetime
import re
import os

class InfoboxUpdater:
    def  __init__(self, site):
        self.site = site

    def get_pages_using_infobox(self):
        """Get all pages that transclude the Infobox Soyjak template."""
        template = pywikibot.Page(self.site, "Template:Infobox Soyjak")
        return template.embeddedin(namespaces=[0, 3006])  # Only search main or SNCA namespace

    @staticmethod
    def get_variant_count(tag: str) -> int:
        url = f"https://soybooru.com/api/internal/autocomplete?s={tag}"
        headers = {
            "User-Agent": os.environ['UA_AGENT']
        }
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        data = res.json()

        if isinstance(data, dict):
            if tag in data:
                return int(data[tag])

            if data:
                first_key = next(iter(data))
                return int(data[first_key])

        return 0

    @staticmethod
    def update_page_variants(self, page: pywikibot.Page):
        """Update booru_posts counts in a page, if outdated."""
        print(f"→ Checking [[{page.title()}]]...")
        original_text = page.text
        wikicode = mwparserfromhell.parse(original_text)
        today_str = datetime.now().strftime("%B %d, %Y").replace(" 0", " ")
        changed = False

        for template in wikicode.filter_templates(recursive=True):
            if template.name.strip().lower() == "infobox soyjak":
                if not template.has("booru_posts"):
                    continue

                raw_value = str(template.get("booru_posts").value)
                subcode = mwparserfromhell.parse(raw_value)

                for subtemplate in subcode.filter_templates(recursive=True):
                    if subtemplate.has(1) and subtemplate.has("display"):
                        variant = subtemplate.get(1).value.strip()
                        display_value = str(subtemplate.get("display").value).strip()
                        current_display = int(display_value.rstrip("+"))  # Strip '+' if present
                        actual_count = self.get_variant_count(variant)

                        if current_display != actual_count and actual_count > 0:
                            print(f"[+] Updating '{variant}': {current_display} → {actual_count}")
                            subtemplate.add("display", str(actual_count))
                            updated_raw_value = self.update_as_of_date(str(subcode), today_str)
                            template.add("booru_posts", updated_raw_value.strip())
                            changed = True

        if changed:
            page.text = str(wikicode)
            page.save(summary="Updated boorusearch post counts")

    @staticmethod
    def update_as_of_date(text: str, new_date: str) -> str:
        # Matches <small>As of ...</small> or <span>As of ...</span>
        pattern = re.compile(r'(<(small|span)\b[^>]*?>)(\s*As of\s+)[^<]+?(</\2>)', re.IGNORECASE)
        return pattern.sub(rf"\1As of {new_date}\4", text)

    # runs updater
    def run(self):
        """Run update on all matching pages."""
        pages = list(self.get_pages_using_infobox())
        print(f"[*] Found {len(pages)} pages using {{Infobox Soyjak}}")

        for page in pages:
            try:
                self.update_page_variants(self, page)
            except Exception as e:
                print(f"[!] Error on {page.title()}: {e}")
        print("[✓] All pages checked.")
