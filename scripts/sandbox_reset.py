import pywikibot


def reset_sandbox(site):
    """Replace the contents of Soyjak Wiki:Sandbox with {{subst:Sandbox}}."""
    print("[*] Resetting sandbox")

    page = pywikibot.Page(site, "Soyjak Wiki:Sandbox")

    try:
        page.text = "{{subst:Sandbox}}"
        page.save(
            summary="Automated sandbox reset",
            minor=False,
        )
        print("[✓] Sandbox reset successfully")
    except Exception as e:
        print(f"[x] Failed to reset sandbox: {e}")
