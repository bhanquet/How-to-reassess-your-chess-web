"""HTML escaping helpers used by the EPUB ingestion pipeline."""


def html_escape(text):
    """Escape special HTML characters.

    Also normalizes the "<;" sequence into "c" before escaping so that a
    cedilla extracted from the source text ("fa<;ade") does not become the
    artifact "&lt;;" ("pawn-fa&lt;;ade"). This also protects entries that
    would bypass the normalization step.
    """
    text = text.replace('<;', 'c')
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')