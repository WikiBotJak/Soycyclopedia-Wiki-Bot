import pywikibot

def ensure_redirect(site, snca_title):
    main_title = snca_title.replace("SNCA:", "").strip()

    if "/" in main_title:
        return

    main_page = pywikibot.Page(site, main_title)
    target_page = pywikibot.Page(site, snca_title)

    if target_page.exists() and not main_page.exists():
        main_page.text = f"#REDIRECT [[{snca_title}]]"
        main_page.save(summary="Auto-created redirect for SNCA page")

def scan_snca_pages(site):
    print(f"[*] Checking for missing SNCA pages redirects...")

    for change in site.recentchanges(namespaces=[3006]):
        if change['type'] != 'new':
            continue

        ensure_redirect(site, change['title'])