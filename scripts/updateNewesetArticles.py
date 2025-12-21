import pywikibot

excluded_prefix = "Featured Gem:Main Page/Featured Gem"
page_title = "Main Page/NA"
max_new_pages = 5


def update_newest_articles(site):
    new_pages = []
    page = pywikibot.Page(site, page_title)

    for change in site.recentchanges(namespaces=0, changetype='new', total=50):
        title = change['title']

        if title.startswith(excluded_prefix) or 'redirect' in change:
            continue

        # Ensure the page still exists (not moved/deleted)
        page_obj = pywikibot.Page(site, title)
        if not page_obj.exists():
            print(f"[!] Skipping missing/deleted: {title}")
            continue

        if page_obj.content_model in ('javascript', 'css'):
            continue

        new_pages.append(f"[[{title}]]")
        if len(new_pages) == max_new_pages:
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
