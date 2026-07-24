def length_check(content: str, max_length: int = 700) -> tuple[bool, int]:
    clean_content = content.strip()
    length = len(clean_content)
    return (length <= max_length, length)
