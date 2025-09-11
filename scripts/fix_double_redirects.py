
import pywikibot
from pywikibot import pagegenerators

def fix_double_redirects(site):
    """
    A double redirect occurs when:
      Page A → Page B → Page C
    This function updates Page A so it redirects directly to Page C.
    """
    # Gets double page redirects
    double_redirects = list(site.double_redirects())
    print(f"[*] Found {len(double_redirects)} double page redirects...")

    for page in double_redirects:
        try:
            if not page.isRedirectPage():
                continue

            # Get the final redirect target
            final_target = page.getRedirectTarget()
            while final_target.isRedirectPage():
                final_target = final_target.getRedirectTarget()

            # If final target is different, fix redirect
            if page.getRedirectTarget() != final_target:
                page.text = f"#REDIRECT [[{final_target.title()}]]"
                page.save(summary=f"Fixed double redirect")
                print(f"[✓] Fixed double redirect {page.title()} → {final_target.title()}")
        except pywikibot.exceptions.IsRedirectPageError:
            continue
        except pywikibot.exceptions.NoPageError:
            continue
        except Exception as e:
            pywikibot.error(f"[!] Error on page {page.title()}: {e}")

def fix_broken_redirects(site):
    """
    Broken redirect:
      Page A → (non-existent page)
    This function deletes Page A to remove the broken redirect.
    """
    broken_redirects = list(site.broken_redirects())
    print(f"[*] Found {len(broken_redirects)} broken redirects...")

    for page in broken_redirects:
        try:
            if not page.isRedirectPage():
                continue

            # Try to get the last moved target
            target_title = page.getRedirectTarget().title()
            target_page = pywikibot.Page(site, target_title)
            final_target = target_page.getRedirectTarget() if target_page.exists() else None

            if final_target and final_target.exists():
                # Update the broken redirect to point to last moved target
                page.text = f"#REDIRECT [[{final_target.title()}]]"
                page.save(summary=f"Fixed broken redirect")
                print(f"[✓] Fixed broken redirect {page.title()} → {final_target.title()}")
            else:
                page.delete(reason="Broken redirect", mark=True)
                print(f"[✓] Marked broken redirect {page.title()} for deletion")


        except Exception as e:
            pywikibot.error(f"[!] Error processing broken redirect {page.title()}: {e}")

def check_redirects(site):
    fix_double_redirects(site)
    fix_broken_redirects(site)
