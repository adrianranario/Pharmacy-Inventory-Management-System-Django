import re


_BULLET_RE = re.compile(r'^(\s*)[*+-]\s+(.*)$')
_HEADING_RE = re.compile(r'^\s*#{1,6}\s*(.*?)\s*#*\s*$')
_RULE_RE = re.compile(r'^\s*[-*_]{3,}\s*$')


def clean_assistant_answer(text):
    """Turn lightweight Markdown from the model into clean plain text."""
    if not text:
        return ''

    text = str(text).replace('\r\n', '\n').replace('\r', '\n')
    lines = []
    for raw_line in text.split('\n'):
        line = raw_line.rstrip()
        if _RULE_RE.match(line):
            lines.append('')
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            line = heading.group(1)

        bullet = _BULLET_RE.match(line)
        if bullet:
            line = f'{bullet.group(1)}• {bullet.group(2)}'

        # Remove bold/italic markers and any stray asterisks or backticks.
        line = line.replace('**', '').replace('*', '').replace('`', '')
        line = re.sub(r'^(\s*•)\s+', r'\1 ', line)
        lines.append(line)

    cleaned = '\n'.join(lines)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    return cleaned
