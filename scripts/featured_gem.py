from dataclasses import fields
from datetime import datetime, timezone
import mwparserfromhell
import pywikibot

SCHEDULE_PAGE = "Main Page/Featured Gem"
OUTPUT_PAGE = "Featured Gem:Static"
OPTION_MAP = {
    "description": "2",
    "height": "3",
    "width": "4",
    "body": "5",
    "bodytext": "6",
    "text": "7",
    "header": "8",
    "border": "9",
    "cross": "10",
    "showsize": "showsize",
}
EXCLUDED_FEATURED_TEMPLATES = {
    "gemerald",
    "gem",
    "topaz",
    "ruby",
    "rust",
    "coal",
    "dust",
    "fossil",
    "previouslyfeatured"
    "tw"
}

def get_param(template, name, default=None):
    if not template.has(name):
        return default

    value = str(template.get(name).value).strip()

    if not value:
        return default
    return value

def parse_featured_date(value):
    try:
        return datetime.strptime(value.strip(), "%B %d, %Y").date()
    except ValueError as exec:
        raise ValueError(f"Invalid Featured Gem date: {value!r}") from exec

def normalize_article(value):
    value = value.strip()
    code = mwparserfromhell.parse(value)

    links = code.filter_wikilinks(
        recursive=False
    )

    if len(links) == 1 and str(code).strip() == str(links[0]).strip():
        return str(links[0].title).strip()

    return value

def parse_featured_template(template):
    date_text = get_param(template, "1")
    article = get_param(template, "2")

    if date_text is None or article is None:
        raise ValueError(
            "Featured Gem requires {{Featured Gem|date|article}}"
        )

    options = {
        OPTION_MAP.get(name.lower(), name): value
        for param in template.params
        if (name := str(param.name).strip()) not in ("1", "2")
        if (value := str(param.value).strip())
    }

    return {
        "date": parse_featured_date(date_text),
        "article": normalize_article(article),
        "options": options
    }


def get_featured_entry(site):
    page = pywikibot.Page(site, SCHEDULE_PAGE)
    code = mwparserfromhell.parse(page.get())

    today = datetime.now(timezone.utc).date()
    candidates = []

    for template in code.filter_templates(recursive=True):
        name = (str(template.name).strip().replace("_", " ").lower())

        if name != "featured gem":
            continue

        try:
            entry = parse_featured_template(template)
        except ValueError as exc:
            print(
                f"[!] Ignoring malformed "
                f"{{{{Featured Gem}}}}: {exc}"
            )
            continue

        # Ignore old schedule entries.
        if entry["date"] < today:
            continue

        candidates.append(entry)

    if not candidates:
        return None

    # Closest scheduled Featured Gem from today onward.
    return min(
        candidates,
        key=lambda entry: entry["date"]
    )

def clean_featured_content(text):
    code = mwparserfromhell.parse(text)
    for template in list(code.filter_templates(recursive=True)):
        name = str(template.name).strip().replace("_", " ").lower()

        if name in EXCLUDED_FEATURED_TEMPLATES:
            code.remove(template, recursive=True)

    for link in list(code.filter_wikilinks(recursive=True)):
        title = str(link.title).strip().replace("_", " ")

        if title.lower().startswith("category:"):
            code.remove(link, recursive=True)

    return str(code).strip()

def escape_table_pipes(text):
    """
    Protect table pipes from being interpreted as parameters of the
    surrounding {{Articlebox/Featured}} template.

    The opening {| is intentionally left alone.
    """
    lines = text.splitlines(keepends=True)
    output = []
    table_depth = 0

    for line in lines:
        stripped = line.lstrip()
        indent = line[:len(line) - len(stripped)]

        # Opening {| MUST remain literal.
        if stripped.startswith("{|"):
            table_depth += 1
            output.append(
                indent + "{" + "{{!}}" + stripped[2:]
            )
            continue

        if table_depth:
            # |}
            if stripped.startswith("|}"):
                output.append(
                    indent + "{{!}}}" + stripped[2:]
                )
                table_depth -= 1
                continue

            # |-, |+, and ordinary table cells
            if stripped.startswith("|"):
                output.append(
                    indent + "{{!}}" + stripped[1:]
                )
                continue

        output.append(line)

    return "".join(output)

def build_static_page(entry,revision_id, article_text):
    article_text = escape_table_pipes(article_text)
    code = mwparserfromhell.parse("{{Articlebox/Featured}}")
    template = code.filter_templates(recursive=False)[0]

    template.add("1", entry["article"])
    template.add("content", "\n" + article_text + "\n")
    for param, value in entry["options"].items():
        template.add(param, value)

    header = (
        "<!--\n"
        "AUTOMATICALLY GENERATED BY SoycyclopediaBot.\n"
        "Do not edit this page manually.\n"
        "\n"
        f"Source: [[{entry['article']}]]\n"
        f"Revision: {revision_id}\n"
        f"Featured date: {entry['date'].isoformat()}\n"
        "-->"
    )

    return header + str(code) + "\n"

def mark_article_featured(page):
    code = mwparserfromhell.parse(page.get())

    # Don't add the Featured Gem icon twice.
    for template in code.filter_templates(recursive=True):
        name = str(template.name).strip().replace("_", " ").lower()

        if name != "PreviouslyFeatured":
            continue

        icon_name = get_param(template, "name")

        if icon_name == "featured-gem":
            return

    icon = (
        "{{PreviouslyFeatured}}\n"
    )

    code.insert(0, icon)

    page.text = str(code)
    page.save(
        summary="Bot: mark article as previously featured",
        minor=True
    )


def publish_featured_gem(site, entry):
    article_name = entry["article"]

    source_page = pywikibot.Page(site, article_name)
    if not source_page.exists():
        raise RuntimeError(
            f"Scheduled Featured Gem does not exist: "
            f"{article_name}"
        )

    # Get the article source as it exists right now.
    article_text = clean_featured_content(source_page.get())
    revision_id = source_page.latest_revision_id

    print(
        f"[*] Publishing Featured Gem: "
        f"{article_name} "
        f"(revision {revision_id})"
    )

    generated_text = build_static_page(entry, revision_id, article_text)

    output_page = pywikibot.Page(
        site,
        OUTPUT_PAGE
    )

    output_page.text = generated_text

    output_page.save(
        summary=(
            f"Publish Featured Gem "
            f"[[{article_name}]] "
            f"(revision {revision_id})"
        ),
        minor=False
    )

    mark_article_featured(source_page)

    print(
        f"[+] Published Featured Gem: "
        f"{article_name} @ revision {revision_id}"
    )


def update_featured_gem(site):
    print("[*] Checking Featured Gem schedule...")

    entry = get_featured_entry(site)

    if entry is None:
        print("[*] No upcoming Featured Gem found.")
        return

    today = datetime.now(timezone.utc).date()
    print(
        f"[*] Next Featured Gem: "
        f"{entry['article']} "
        f"({entry['date'].isoformat()})"
    )

    # It's upcoming, but not due yet.
    if entry["date"] != today:
        return

    publish_featured_gem(site, entry)
