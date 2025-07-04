import pywikibot
from datetime import datetime

class MainPageArticleUpdater:
    def __init__(self, site):
        self.site = site
        self.excluded_prefix = "Featured Gem:Main Page/Featured Gem"
        self.page_title = "Main Page/NA"
        self.max_new_pages = 5

    def run(self):
        new_pages = []
        page = pywikibot.Page(self.site, self.page_title)

        for change in self.site.recentchanges(namespaces=0, changetype='new', total=20):
            title = change['title']
            if title.startswith(self.excluded_prefix) or 'redirect' in change:
                continue
            new_pages.append(f"[[{title}]]")
            if len(new_pages) == self.max_new_pages:
                break

        # Build post content
        joined_links = " • ".join(new_pages)

        post = f"""<div style="text-align: center;">
            <div style="display: inline-block; text-align: left;">
        {{{{Post|'''{joined_links}'''
        
        |Soot|Sun 20 Sep 2020 16:41:15|soy|1|700}}}}
            </div>
        </div>"""

        # Update the wiki page
        print(f"Updating newest mainspace articles ({joined_links})")
        page.text = post
        page.save(summary="Update newest mainspace articles")