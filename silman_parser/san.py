"""Chess notation (SAN) cleanup extracted from the EPUB text."""

import re


def normalize_unicode_artifacts(text):
    """Fix the EPUB unicode artifacts shared by all the notation paths.

    Ellipsis "…" -> "...", castling with unicode dashes ("0–0", "0—0",
    "0-0", with the 0/O variants) -> O-O / O-O-O. The three-piece form must
    be replaced before the two-piece one ("0-0-0" would otherwise match
    "0-0" first and leave a residual "-0").
    """
    text = text.replace('\u2026', '...')
    text = re.sub(r'\b(?:0|O)\s*[\u2013\u2014-]\s*(?:0|O)\s*[\u2013\u2014-]\s*(?:0|O)\b', 'O-O-O', text)
    text = re.sub(r'\b(?:0|O)\s*[\u2013\u2014-]\s*(?:0|O)\b', 'O-O', text)
    return text


def normalize_move_text(text):
    """Clean the book notation into a single-space token stream.

    Strips tags, parentheticals and annotations, fixes the EPUB unicode
    artifacts (see normalize_unicode_artifacts), repairs OCR move-number
    artifacts, and finally removes the move numbers and results so that only
    the SAN tokens remain (extract_san_moves then filters them).
    """
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\([^)]*\)', ' ', text)
    text = re.sub(r'[!?]+', '', text)
    text = normalize_unicode_artifacts(text)
    text = re.sub(r'\bl\s*\.\s*', '1. ', text)
    text = re.sub(r'\bll\s*\.\s*', '11. ', text)
    text = re.sub(r'\bIll\s*\.\s*', '111. ', text)
    text = re.sub(r'\bII\s*\.\s*', '11. ', text)
    text = re.sub(r'\bIII\s*\.\s*', '111. ', text)
    text = re.sub(r'\b(\d)\s+(\d)\s*\.', r'\1\2.', text)
    text = re.sub(r'([a-h][1-8]|[+#]|=[QRBN]|O-O|O-O-O)(\d{1,3}\.)', r'\1 \2', text)
    # "hxg62 3.Nxg6" -> "hxg6 23.Nxg6" (move number glued after a move)
    text = re.sub(r'([a-h][1-8])(\d{1,2})\s+(\d{1,2})\.', r'\1 \2\3.', text)
    text = re.sub(r'([a-h1-8QRBN])(O-O)', r'\1 \2', text)
    text = re.sub(r'([a-h][1-8])S\b', r'\g<1>8', text)
    text = re.sub(r'([RNBQK][a-h1-8]*)S\b', r'\g<1>8', text)
    text = re.sub(r'\b([a-h])S\b', r'\g<1>5', text)
    text = re.sub(r'([RNBQK][a-h1-8]*)l\b', r'\g<1>1', text)
    text = re.sub(r'\b([a-h])l\b', r'\g<1>1', text)
    # Residual move number artifacts "SO."/"Sl."/"S 1." -> "50."/"51."/...
    # (purged just below by the number removal).
    text = re.sub(r'\bS[O0]\.', '50.', text)
    text = re.sub(r'\bSl\.', '51.', text)
    text = re.sub(r'\bS1\.', '51.', text)
    # Results BEFORE the number removal: otherwise r'\d+\.' eats the
    # "1."/".0." of "0-1."/"1-0." and the result no longer matches and comes
    # out as a residual "0-"/"1-".
    text = re.sub(r'\b(1-0|0-1|1/2-1/2|\*)\b', ' ', text)
    text = re.sub(r'\d+\.\.\.', ' ', text)
    text = re.sub(r'\d+\.', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


_MOVE_RE = re.compile(
    r'^(?:[KQRBNP]?[a-h]?[1-8]?x?[a-h][1-8](?:=[QRBN])?|O-O(?:-O)?)[+#]?$')


def extract_san_moves(text):
    """Extract the SAN move tokens from a notation text.

    Normalizes the text (see normalize_move_text) then keeps only the tokens
    matching the SAN shape (_MOVE_RE): piece/pawn moves, captures, promotions
    and castling, with an optional check/mate suffix. Non-move tokens
    (diagram labels, prose, residual numbers) are dropped.
    """
    text = normalize_move_text(text)
    if not text:
        return []
    return [tok for tok in text.split() if _MOVE_RE.match(tok)]