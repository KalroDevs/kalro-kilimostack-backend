MAX_CHUNK_CHARS = 1800


def split_long_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [paragraph.strip() for paragraph in text.split("\n") if paragraph.strip()] or [text]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        if len(current) + len(paragraph) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = paragraph
        else:
            current = f"{current}\n{paragraph}".strip()
    if current:
        chunks.append(current.strip())
    return chunks
