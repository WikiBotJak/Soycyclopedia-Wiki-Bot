from pywikibot.family import Family

class Family(Family):
    name = 'soyjak'
    langs = {
        'en': 'wiki.soyjak.st',
    }

    def scriptpath(self, code):
        return ''  # no /w or /wiki directory in URL

    def protocol(self, code):
        return 'https'