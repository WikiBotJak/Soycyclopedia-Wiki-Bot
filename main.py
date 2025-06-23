import pywikibot

def main():
    site = pywikibot.Site()
    if not site.logged_in():
        site.login()
    print(f"Logged in as: {site.user()}")

    # Proceed with tasks...

if __name__ == '__main__':
    main()