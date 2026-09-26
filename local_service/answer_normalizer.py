"""Deterministic transcription cleanup; never evaluates or grades mathematics."""
import re
import unicodedata


def normalize_answer(raw):
    if raw is None:
        return {"raw": None, "normalized": None, "rules_applied": []}
    if not isinstance(raw, str):
        raise TypeError("raw answer must be text")
    text = raw
    rules = []
    filtered = ''.join(c for c in text if c in '\t\n\r' or unicodedata.category(c) != 'Cc')
    if filtered != text:
        text = filtered;rules.append('CONTROL_CHARACTERS')
    normalized = unicodedata.normalize('NFKC', text)
    if normalized != text:
        rules.append('UNICODE_NFKC');text = normalized
    stripped = re.sub(r'\s+', ' ', text).strip()
    if stripped != text:
        rules.append('WHITESPACE');text = stripped
    replaced = re.sub(r'(?<=[0-9])\s*[×Xx]\s*(?=[0-9])', '*', text).replace('×','*')
    if replaced != text:
        rules.append('MULTIPLY_SIGN');text = replaced
    replaced = text.replace('÷','/')
    if replaced != text:
        rules.append('DIVIDE_SIGN');text = replaced
    return {"raw": raw, "normalized": text, "rules_applied": rules}
