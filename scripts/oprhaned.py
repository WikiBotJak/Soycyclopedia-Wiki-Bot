import pywikibot
import mwparserfromhell

def get_orphan_template(code):
    return next(
        (
            template
            for template in code.filter_templates()
            if template.name.matches("Orphan")
        ),
        None
    )

def add_orphan(page):
    text = page.get()

    page.text = "{{Orphan}}\n" + text
    page.save(
        summary="Marking orphaned article",
        minor=True
    )

    print(f"[+] Added {{Orphan}}: {page.title()}")

def remove_orphan(page):
    text = page.get()
    code = mwparserfromhell.parse(text)

    orphan = get_orphan_template(code)

    if orphan is None:
        return

    code.remove(orphan)

    page.text = str(code).lstrip("\n")
    page.save(
        summary="Removing orphaned article tag",
        minor=True
    )

    print(f"[-] Removed {{Orphan}}: {page.title()}")

def update_orphaned_pages(site):
    print("[*] Checking for orphaned articles...")


    orphan_template = pywikibot.Page(site, "Template:Orphan")

    # Pages MediaWiki currently considers lonely.
    lonely= {
        page.title(): page
        for page in site.lonelypages()
        if page.namespace() == 0 and not page.isRedirectPage() and not page.isDisambig()
    }
    # Pages that currently transclude {{Orphan}}.
    tagged = {
        page.title(): page
        for page in orphan_template.getReferences(only_template_inclusion=True, namespaces=[0])
    }

    # Lonely now, but doesn't have {{Orphan}}.
    for title in lonely.keys() - tagged.keys():
        page = lonely[title]

        try:
            add_orphan(page)
        except Exception as exc:
            print(f"[!] Failed tagging {title}: {exc}")
    # Has {{Orphan}}, but isn't lonely anymore.
    for title in tagged.keys() - lonely.keys():
        page = tagged[title]

        try:
            remove_orphan(page)
        except Exception as exc:
            print(f"[!] Failed untagging {title}: {exc}")

    print(
        f"[*] Orphan check complete: "
        f"{len(lonely)} lonely pages, "
        f"{len(tagged)} tagged pages."
    )