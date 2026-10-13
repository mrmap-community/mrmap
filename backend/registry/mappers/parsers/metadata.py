from registry.models.metadata import Keyword


def parse_keyword(mapper, element):
    """Ignore blank keywords without changing the text of valid keywords."""
    keyword = element.text
    if keyword and keyword.strip():
        return Keyword(keyword=keyword)
