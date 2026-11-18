"""Update the Community Missions schedule.

The bot reads nominations and poll results on Discussion. SQLite holds the
schedule and decisions, and the wiki pages display that state.
"""

import difflib
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape, unescape
from html.parser import HTMLParser
from pathlib import Path

import mwparserfromhell
import pywikibot
from pywikibot.exceptions import APIError

PROJECT = "Soyjak Wiki:Community missions"
DISCUSSION = "Soyjak Wiki talk:Community missions"
CURRENT = f"{PROJECT}/Current"
UPCOMING = f"{PROJECT}/Upcoming"
ARCHIVE = f"{PROJECT}/Archive"
DATABASE_PATH = Path(__file__).resolve().parents[1] / ".Soycyclopedia-Bot-DB.sqlite3"
VOTING_WINDOW = timedelta(hours=48)
SUMMARY = "Update community mission display from the schedule"
NOMINATION_PREFIX = "Mission nomination:"
NOMINATION_TEMPLATE = "Community mission nomination"
ARTICLE_TEMPLATE = "Community mission article"
MISSION_COLUMNS = (
    "poll_id", "section", "title", "objective", "scope", "days", "nominated_at", "closed_at",
    "yays", "nays", "starts_at", "finished_at", "markers_resolved",
)


def open_mission_database(path):
    # SQLite holds the schedule
    database = sqlite3.connect(path, timeout=30)
    try:
        database.row_factory = sqlite3.Row
        database.execute("PRAGMA foreign_keys = ON")
        database.executescript("""
            CREATE TABLE IF NOT EXISTS missions (
                poll_id TEXT PRIMARY KEY COLLATE NOCASE NOT NULL,
                section TEXT NOT NULL,
                title TEXT NOT NULL,
                objective TEXT NOT NULL,
                scope TEXT NOT NULL,
                days INTEGER NOT NULL CHECK (days >= 1),
                nominated_at TEXT,
                closed_at TEXT,
                yays INTEGER CHECK (yays >= 0),
                nays INTEGER CHECK (nays >= 0),
                starts_at TEXT,
                finished_at TEXT,
                archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
                markers_resolved INTEGER NOT NULL CHECK (markers_resolved IN (0, 1)),
                CHECK ((yays IS NULL) = (nays IS NULL)),
                CHECK (yays IS NULL OR closed_at IS NOT NULL),
                CHECK (finished_at IS NULL OR starts_at IS NOT NULL)
            );
            CREATE TABLE IF NOT EXISTS mission_articles (
                poll_id TEXT NOT NULL REFERENCES missions (poll_id) ON DELETE CASCADE,
                talk_page TEXT NOT NULL,
                PRIMARY KEY (poll_id, talk_page)
            );
        """)
        return database
    except (OSError, sqlite3.Error):
        database.close()
        raise


@dataclass
class Mission:
    poll_id: str
    section: str
    title: str
    objective: str
    scope: str
    days: int
    nominated_at: datetime | None = None
    closed_at: datetime | None = None
    yays: int | None = None
    nays: int | None = None
    starts_at: datetime | None = None
    finished_at: datetime | None = None
    marker_pages: tuple[str, ...] | None = None

    @property
    def accepted(self):
        if self.yays is None:
            return self.starts_at is not None  # Imported schedules may lack tallies.
        return self.yays > 0 and 5 * self.yays >= 6 * self.nays

    @property
    def ends_at(self):
        return self.starts_at + timedelta(days=self.days) if self.starts_at is not None else None

    @property
    def decided(self):
        return self.closed_at is not None or self.starts_at is not None


def load_missions(database):
    missions = {}
    for row in database.execute("SELECT * FROM missions WHERE archived = 0 ORDER BY poll_id"):
        values = {key: row[key] for key in MISSION_COLUMNS[:-1]}
        for key in ("nominated_at", "closed_at", "starts_at", "finished_at"):
            if values[key] is not None:
                values[key] = utc(values[key])
        key = row["poll_id"].lower()
        if row["markers_resolved"]:
            values["marker_pages"] = tuple(
                title
                for (title,) in database.execute(
                    "SELECT talk_page FROM mission_articles WHERE poll_id = ? ORDER BY talk_page",
                    (row["poll_id"],),
                )
            )
        missions[key] = Mission(**values)
    return missions


def store_mission(database, mission):
    columns = ", ".join(MISSION_COLUMNS)
    placeholders = ", ".join("?" for _ in MISSION_COLUMNS)
    assignments = ", ".join(f"{name} = excluded.{name}" for name in MISSION_COLUMNS[1:])
    values = [getattr(mission, name) for name in MISSION_COLUMNS[:-1]]
    values = [wiki_timestamp(value) if isinstance(value, datetime) else value for value in values]
    database.execute(
        f"INSERT INTO missions ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT (poll_id) DO UPDATE SET {assignments}",
        (*values, int(mission.marker_pages is not None)),
    )
    database.execute("DELETE FROM mission_articles WHERE poll_id = ?", (mission.poll_id,))
    database.executemany(
        "INSERT INTO mission_articles (poll_id, talk_page) VALUES (?, ?)",
        ((mission.poll_id, title) for title in mission.marker_pages or ()),
    )


def read_nominations(source):
    code = mwparserfromhell.parse(source)
    uses = Counter(poll_id.lower() for tag in polls(code) if (poll_id := tag_poll_id(tag)))
    result = {}
    for section in code.get_sections(levels=[2], include_lead=False):
        heading = nomination_heading(section)
        if heading is None:
            continue
        try:
            title = heading.removeprefix(NOMINATION_PREFIX).strip()
            if not title or not plain_heading(heading):
                raise ValueError("replace the subject placeholder with a plain nomination title")
            tags = polls(section)
            if len(tags) != 1 or unescape(str(tags[0].contents)).split() != [
                "Accept", "this", "mission?", "Yay", "Nay",
            ]:
                raise ValueError("expected one saved Accept this mission? Yay/Nay poll")
            poll_id = tag_poll_id(tags[0])
            if poll_id is None or uses[poll_id.lower()] != 1:
                raise ValueError("expected a unique 32-character poll ID")
            index = next((index for index, node in enumerate(section.nodes) if node is tags[0]), None)
            if index is None:
                raise ValueError("the poll must be placed directly in the nomination")
            fields = nomination_fields(mwparserfromhell.wikicode.Wikicode(section.nodes[:index]))
            days = fields.get("days", "")
            objective, scope = fields.get("objective", ""), fields.get("scope", "")
            if not objective or not scope or len(objective.splitlines()) != 1 or len(scope.splitlines()) != 1:
                raise ValueError("objective and scope must each be a nonempty single line")
            days = int(days)
            if days < 1:
                raise ValueError("duration must be at least one day")
            result[poll_id.lower()] = Mission(poll_id, heading, title, objective, scope, days)
        except ValueError as error:
            print(f"Skipped {heading}: {error}", file=sys.stderr)
    return result



def close_due_polls(site, discussion, revision, missions, known_poll_ids, now):
    candidates = {
        key: mission for key, mission in read_nominations(discussion).items()
        if key not in known_poll_ids
    }
    if not candidates:
        return

    dates = nomination_dates(site, revision, candidates)
    due = []
    for key, mission in candidates.items():
        mission.nominated_at = utc(dates[key])
        if now >= mission.nominated_at + VOTING_WINDOW:
            due.append(mission)
    if not due:
        return

    counts = observed_votes(site, revision)
    for mission in due:
        yays = counts.get((mission.poll_id, "1"), [])
        nays = counts.get((mission.poll_id, "2"), [])
        if len(yays) != 1 or len(nays) != 1:
            print(f"Deferred {mission.section}: Yay/Nay counts unavailable.", file=sys.stderr)
            continue
        mission.closed_at = now
        mission.yays, mission.nays = yays[0], nays[0]
        missions[mission.poll_id.lower()] = mission


def assign_dates(missions, now):
    scheduled = sorted(
        (mission for mission in missions.values() if mission.starts_at is not None),
        key=lambda mission: mission.starts_at,
    )
    for earlier, later in zip(scheduled, scheduled[1:]):
        if later.starts_at < earlier.ends_at:
            raise ValueError(f"Overlapping missions: {earlier.title!r} and {later.title!r}")

    next_start = max(now, scheduled[-1].ends_at) if scheduled else now
    waiting = sorted(
        (mission for mission in missions.values() if mission.accepted and mission.starts_at is None),
        key=lambda mission: (mission.nominated_at or mission.closed_at, mission.poll_id),
    )
    for mission in waiting:
        mission.starts_at = next_start
        next_start = mission.ends_at
        scheduled.append(mission)
    for mission in scheduled:
        if mission.ends_at <= now:
            mission.finished_at = mission.ends_at
    return scheduled


def tag_poll_id(tag):
    value = next((str(attr.value).strip() for attr in tag.attributes
                  if str(attr.name).strip().lower() == "id"), "")
    return value if len(value) == 32 else None


def polls(code):
    return code.filter_tags(matches=lambda tag: str(tag.tag).strip().lower() == "poll")


def nomination_heading(section):
    headings = section.filter_headings(recursive=False)
    if headings and headings[0].level == 2:
        title = str(headings[0].title).strip()
        if title.startswith(NOMINATION_PREFIX):
            return title
    return None


def plain_heading(title):
    return not any(char in "[]{}|<>#" or ord(char) < 32 or ord(char) == 127 for char in title)


def nomination_templates(code):
    return code.filter_templates(
        recursive=False, matches=lambda template: template.name.matches(NOMINATION_TEMPLATE),
    )


def nomination_fields(section):
    templates = nomination_templates(section)
    if templates:
        template = templates[0]
        return {key: str(template.get(key).value).strip()
                for key in ("objective", "scope", "days") if template.has(key)}

    # Older nominations saved these labels as list items during substitution.
    labels = {"Objective": "objective", "Pages or category": "scope", "Proposed duration": "days"}
    fields = {}
    for line in str(section).splitlines():
        label, separator, value = line.partition(":'''")
        if separator and label.startswith("* '''"):
            key = labels.get(label.removeprefix("* '''"))
            if key:
                fields.setdefault(key, value.strip())
    days = fields.get("days", "")
    fields["days"] = days.removesuffix(" days").removesuffix(" day")
    return fields


def read_page(site, title):
    page = pywikibot.Page(site, title)
    try:
        text = page.get(get_redirect=True)
    except pywikibot.exceptions.NoPageError:
        return None, {}
    return text, {"baserevid": page.latest_revision_id}


class PollResults(HTMLParser):
    """Read integer counts from AJAXPoll answer bars in rendered page HTML."""

    def __init__(self):
        super().__init__()
        self.answer = None
        self.in_result = False
        self.in_count = False
        self.counts = {}

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        classes = attrs.get("class", "").split()
        if "ajaxpoll-answer" in classes:
            self.answer = (attrs.get("poll"), attrs.get("answer"))
            self.in_result = False
        if "ajaxpoll-answer-vote" in classes:
            self.in_result = True
        if tag == "span" and self.in_result:
            self.in_count = True
            self.in_result = False

    def handle_endtag(self, tag):
        if tag == "span":
            self.in_count = False

    def handle_data(self, data):
        if self.in_count and self.answer and data.strip().isascii() and data.strip().isdecimal():
            self.counts.setdefault(self.answer, []).append(int(data))


def observed_votes(site, revision):
    # Page.get_parsed_page() only renders the current revision.
    result = site.simple_request(
        action="parse", oldid=revision, prop="text", formatversion=2,
        maxage=0, smaxage=0,
    ).submit()
    parser = PollResults()
    parser.feed(result["parse"]["text"])
    return parser.counts


def nomination_dates(site, revision_id, poll_ids):
    """Walk back to the introduction of each poll in the current page history."""
    pending = set(poll_ids)
    dates = {}
    page = pywikibot.Page(site, DISCUSSION)
    for revision in page.revisions():

        if not dates and revision.revid != revision_id:
            continue

        present = {identifier.lower() for tag in polls(mwparserfromhell.parse(page.getOldVersion(revision.revid))) #identify the revision where each poll first appeared. Gets the discussion snapshot the bot is processing
                    if (identifier := tag_poll_id(tag))}
        for poll_id in tuple(pending):
            if poll_id in present:
                dates[poll_id] = wiki_timestamp(revision.timestamp)
            elif poll_id in dates:
                pending.remove(poll_id)
            else:
                raise ValueError("A poll is missing from the Discussion revision being processed.")
        if not pending:
            break
    if not dates:
        raise ValueError(f"Discussion revision {revision_id} was not found.")
    return dates


def template_value(template, name, default=""):
    if not template.has(name):
        return default
    value = template.get(name).value
    nodes = [node for node in value.nodes if str(node).strip()]
    if len(nodes) == 1 and isinstance(nodes[0], mwparserfromhell.nodes.Tag):
        if nodes[0].tag.matches("nowiki"):
            return unescape(str(nodes[0].contents))
    return str(value).strip()


def read_closing_tally(section):
    for line in str(section).splitlines():
        if line.startswith(": Voting is closed. "):
            line = ": " + line.removeprefix(": Voting is closed. ")
        if not line.startswith((": '''Accepted.''' ", ": '''Did not qualify.''' ")):
            continue
        _, found, result = line.partition("Closed tally on ")
        date, timestamp_end, tally = result.partition(" UTC: ")
        yays, separator, remainder = tally.partition(" Yay, ")
        nays, end, _ = remainder.partition(" Nay.")
        if not (found and timestamp_end and separator and end):
            continue
        if not all(count.isascii() and count.isdecimal() for count in (yays, nays)):
            continue
        for date_format in ("%B %d, %Y at %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                closed_at = datetime.strptime(date.replace("'''", ""), date_format)
            except ValueError:
                continue
            return {"closed_at": wiki_timestamp(closed_at), "yays": int(yays), "nays": int(nays)}
    return {}


def read_wiki_missions(discussion, known_poll_ids=()):
    entries = {}
    code = mwparserfromhell.parse(discussion)
    for section in code.get_sections(levels=[2], include_lead=False):
        heading = nomination_heading(section)
        templates = nomination_templates(section)
        tags = polls(section)
        identifier = tag_poll_id(tags[0]) if len(tags) == 1 else None
        if not heading or not identifier or not templates:
            continue
        poll_key = identifier.lower()
        if poll_key in known_poll_ids:
            continue
        template = templates[0]
        result = read_closing_tally(section)
        if not result:
            continue
        entry = entries.get(poll_key)
        if entry is not None:
            entry.update(result)
        else:
            entries[poll_key] = {
                "poll_id": identifier, "section": heading,
                "title": heading.removeprefix(NOMINATION_PREFIX).strip(),
                "objective": template_value(template, "objective"),
                "scope": template_value(template, "scope"),
                "days": int(template_value(template, "days")),
            } | result
    return {
        poll_key: Mission(**(entry | {"closed_at": utc(entry["closed_at"])}))
        for poll_key, entry in entries.items()
    }


def utc(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def wiki_timestamp(value):
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def literal(value):
    return f"<nowiki>{escape(value, quote=False)}</nowiki>"


def display_timestamp(value, *, seconds=False):
    date = f"{value:%B} {value.day}, {value.year}"
    time = value.strftime("%H:%M:%S" if seconds else "%H:%M")
    return f"{date} at {time} UTC"


def display_scope(value):
    scope = []
    for node in mwparserfromhell.parse(value).nodes:
        target = str(node.title).strip().lstrip(":") if isinstance(node, mwparserfromhell.nodes.Wikilink) else ""
        scope.append(f"[[:{target}]]" if target and plain_heading(target) else literal(str(node)))
    return "".join(scope)


def mission_line(mission):
    title = f"[[{DISCUSSION}#{mission.section}|{literal(mission.title)}]]"
    return (
        f"'''{title}''' — {literal(mission.objective)}. "
        f"Scope: {display_scope(mission.scope)}."
    )



def render_schedule(scheduled, now):
    current = "'''No mission is active.'''"
    upcoming = []
    archive = {}
    for mission in scheduled:
        dates = f"{display_timestamp(mission.starts_at)} – {display_timestamp(mission.ends_at)}"
        if mission.finished_at is not None:
            months = archive.setdefault(mission.finished_at.year, {})
            records = months.setdefault(mission.finished_at.month, [])
            anchor = f'<span id="community-mission-{mission.poll_id}"></span>'
            records.append(
                f"* {anchor}{mission_line(mission)} ({dates}). '''Outcome:''' ''Awaiting a summary.''"
            )
        elif mission.starts_at <= now:
            current = f"{mission_line(mission)}<br />'''Ends:''' {display_timestamp(mission.ends_at)}"
        else:
            upcoming.append(f"* {mission_line(mission)} ({dates})")

    views = {}
    for year, months in sorted(archive.items(), reverse=True):
        sections = []
        for month, records in sorted(months.items(), reverse=True):
            heading = datetime(year, month, 1).strftime("%B")
            sections.append(f"== {heading} ==\n" + "\n".join(reversed(records)))
        views[f"{ARCHIVE}/{year}"] = "\n\n".join(sections)
    if archive:
        views[ARCHIVE] = "\n".join(f"* [[{ARCHIVE}/{year}|{year}]]" for year in sorted(archive, reverse=True))
    views[CURRENT] = current
    views[UPCOMING] = "\n\n".join(upcoming) or "No upcoming missions."
    return views


def append_lines(text, addition):
    if not text:
        return addition + "\n"
    return text + ("" if text.endswith("\n") else "\n") + "\n" + addition + "\n"


def merge_archive_index(current, content):
    if not content:
        return current
    targets = {str(link.title).strip().replace("_", " ")
               for link in mwparserfromhell.parse(current or "").filter_wikilinks()}
    additions = []
    for line in content.splitlines():
        link, = mwparserfromhell.parse(line).filter_wikilinks()
        if str(link.title) not in targets:
            additions.append(line)
    if not additions:
        return current
    code = mwparserfromhell.parse(current or "")
    for heading in code.filter_headings(recursive=False):
        if heading.level == 2 and str(heading.title).strip().casefold() == "earlier system":
            code.insert_before(heading, "\n".join(additions) + "\n\n", recursive=False)
            return str(code)
    return append_lines(current or "", "\n".join(additions))


def archive_record_key(line):
    _, anchor, identifier = line.partition('<span id="community-mission-')
    if anchor:
        return identifier.partition('"')[0]
    _, marker, record = line.rpartition(f"[[{DISCUSSION}#")
    key, end, _ = record.partition(" UTC).")
    return key if marker and end else line

def merge_archive_year(current, content):
    if not current:
        return content + "\n"
    sections = mwparserfromhell.parse(current).get_sections(levels=[2], include_lead=True)
    blocks = [str(section) for section in sections]
    months = {}
    new_months = []
    for index, section in enumerate(sections):
        headings = section.filter_headings(recursive=False)
        if headings and headings[0].level == 2:
            months.setdefault(str(headings[0].title).strip().casefold(), index)
    for section in mwparserfromhell.parse(content).get_sections(levels=[2], include_lead=False):
        heading, *records = str(section).strip().splitlines()
        month = heading.strip("= ").casefold()
        if month not in months:
            new_months.append("\n".join([heading, *records]))
            continue
        index = months[month]
        existing = {archive_record_key(line) for line in blocks[index].splitlines()}
        additions = [record for record in records if archive_record_key(record) not in existing]
        if additions:
            header, _, body = blocks[index].partition("\n")
            blocks[index] = header + "\n" + "\n".join(additions) + "\n" + body
    merged = "".join(blocks)
    return append_lines(merged, "\n\n".join(new_months)) if new_months else merged


def update_discussion(source, missions):
    code = mwparserfromhell.parse(source)
    uses = Counter(poll_id.lower() for tag in polls(code) if (poll_id := tag_poll_id(tag)))
    sections = []
    for section in code.get_sections(levels=[2], include_lead=True):
        text = str(section)
        tags = polls(section) if nomination_heading(section) else []
        poll_id = tag_poll_id(tags[0]) if len(tags) == 1 else None
        key = poll_id.lower() if poll_id else None
        mission = missions.get(key) if uses[key] == 1 else None
        if mission is None or not mission.decided:
            sections.append(text)
            continue

        templates = nomination_templates(section)
        if templates:
            template = templates[0]
        else:
            template = mwparserfromhell.nodes.Template(NOMINATION_TEMPLATE)
            for key in ("objective", "scope", "days"):
                template.add(key, str(getattr(mission, key)))
            before, _, after = text.partition(str(tags[0]))
            labels = ("* '''Objective:'''", "* '''Pages or category:'''",
                      "* '''Proposed duration:'''")
            before = "".join(line for line in before.splitlines(keepends=True)
                             if not line.startswith(labels))
            section = mwparserfromhell.parse(before + str(template) + "\n\n" + str(tags[0]) + after)
            template = nomination_templates(section)[0]

        for name in ("nominated", "closed", "yays", "nays", "mission_days", "marker_pages", "start", "finished"):
            if template.has(name):
                template.remove(name)
        text = str(section)
        if mission.yays is not None and not read_closing_tally(section):
            yays, nays = mission.yays, mission.nays
            decision = "Accepted" if mission.accepted else "Did not qualify"
            stamp = display_timestamp(mission.closed_at, seconds=True)
            tally = f"Closed tally on {stamp}: {yays} Yay, {nays} Nay."
            if yays + nays == 0:
                margin = "No votes were cast."
            elif yays == nays:
                margin = "Yay and Nay tied (0 percentage points apart)."
            else:
                leader = "Yay" if yays > nays else "Nay"
                gap = f"{100 * abs(yays - nays) / (yays + nays):.2f}".rstrip("0").rstrip(".")
                unit = "percentage point" if gap == "1" else "percentage points"
                margin = f"{leader} led by {gap} {unit}."
            reply = f": '''{decision}.''' {tally} {margin} ~~~~"
            text = text.rstrip("\n") + f"\n\n{reply}\n\n"
        sections.append(text)
    return "".join(sections)


def find_article_talk_pages(site, scope):
    from pywikibot.exceptions import InvalidTitleError

    targets = [str(link.title) for link in mwparserfromhell.parse(scope).filter_wikilinks()]
    if not targets and plain_heading(scope):
        targets = [scope]
    titles = set()
    for target in targets:
        try:
            article = pywikibot.Page(site, target.strip().lstrip(":"))
            if article.site == site and article.namespace() == 0 and article.exists():
                titles.add(article.toggleTalkPage().title())
        except InvalidTitleError:
            continue
    return tuple(sorted(titles))


def update_article_markers(site, scheduled, now):
    by_page = {}
    for mission in scheduled:
        active = mission.starts_at <= now < mission.ends_at
        if active and mission.marker_pages is None:
            mission.marker_pages = find_article_talk_pages(site, mission.scope)
        for title in mission.marker_pages or ():
            if not title.startswith("Talk:") or not title.removeprefix("Talk:").strip() or not plain_heading(title):
                raise ValueError(f"Invalid marker talk page {title!r}")
            by_page.setdefault(title, []).append((mission, active))

    edits = []
    for title, markers in sorted(by_page.items()):
        old, guard = read_page(site, title)
        new = old or ""
        for mission, active in sorted(markers, key=lambda marker: marker[1]):
            code = mwparserfromhell.parse(new)
            notices = [
               template for template in code.filter_templates(recursive=False)
               if template.name.matches(ARTICLE_TEMPLATE)
               and template_value(template,"poll_id").casefold() == mission.poll_id.casefold()
            ]
            if active:
                task = literal(mission.objective)
                if notices:
                    notice = notices.pop(0)
                    if template_value(notice, "task") != mission.objective:
                        notice.add("task", task)
                else:
                    new = f"{{{{{ARTICLE_TEMPLATE}|poll_id={mission.poll_id}|task={task}}}}}\n{new}"
                    continue

            for template in notices:
                code.remove(template, recursive=False)
            new = str(code)
        if new != (old or ""):
            edits.append(Edit(title, old, new, guard))
    return edits


@dataclass
class Edit:
    title: str
    old: str | None
    new: str
    guard: dict


def plan_changes(site, missions, now, archived_poll_ids=()):
    discussion, guard = read_page(site, DISCUSSION)
    if discussion is None:
        raise ValueError(f"Could not find {DISCUSSION}.")
    revision = guard["baserevid"]
    display_pages = {title: read_page(site, title) for title in (UPCOMING, CURRENT)}
    known_poll_ids = set(missions).union(archived_poll_ids)
    missions.update(read_wiki_missions(discussion, known_poll_ids))
    close_due_polls(
        site, discussion, revision, missions, known_poll_ids.union(missions), now
    )

    scheduled = assign_dates(missions, now)
    edits = update_article_markers(site, scheduled, now)
    updated = update_discussion(discussion, missions)
    if updated != discussion:
        edits.insert(0, Edit(DISCUSSION, discussion, updated, guard))

    for title, content in render_schedule(scheduled, now).items():
        old, guard = display_pages[title] if title in display_pages else read_page(site, title)
        if title == ARCHIVE:
            new = merge_archive_index(old, content)
        elif title.startswith(f"{ARCHIVE}/"):
            new = merge_archive_year(old, content)
        else:
            new = content + "\n"
        if old is None or old.rstrip("\n") != new.rstrip("\n"):
            edits.append(Edit(title, old, new, guard))
    return edits, revision


def publish_edits(site, edits):
    for edit in edits:
        page = pywikibot.Page(site, edit.title)
        page.text = edit.new
        page.save(
            summary=SUMMARY, watch="nochange", minor=False
        )
        print(f"Saved {edit.title}")
        if edit.title == CURRENT:
            site.purgepages([pywikibot.Page(site, PROJECT), pywikibot.Page(site, "Main Page")])
    print(f"Updated {len(edits)} page(s).")

def run_community_missions(site):
    now = datetime.now().astimezone(timezone.utc)
    with closing(open_mission_database(DATABASE_PATH)) as database, database:
        database.execute("BEGIN IMMEDIATE")
        missions = load_missions(database)
        before = {key: vars(mission).copy() for key, mission in missions.items()}
        archived_poll_ids = {
            poll_id.lower() for (poll_id,) in database.execute("SELECT poll_id FROM missions WHERE archived = 1")
        }
        edits, discussion_revision = plan_changes(site, missions, now, archived_poll_ids)

        if read_page(site, DISCUSSION)[1].get("baserevid") != discussion_revision:
            raise ValueError("The Discussion page changed during preflight. Run again.")
        # Commit decisions before making any wiki edits so a retry keeps the closing tally.
        for key, mission in missions.items():
            if vars(mission) != before.get(key):
                store_mission(database, mission)
        finished = [(mission.poll_id,) for mission in missions.values() if mission.finished_at is not None]
        database.executemany(
            "UPDATE missions SET archived = 1 WHERE poll_id = ? AND finished_at IS NOT NULL",
            finished,
        )
        database.commit()

        publish_edits(site, edits)
