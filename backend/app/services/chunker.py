from dataclasses import dataclass


@dataclass
class ChunkData:
    chunk_index: int
    content: str


def split_text_into_chunks(text: str, chunk_size: int = 500) -> list[ChunkData]:
    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[ChunkData] = []
    start = 0
    chunk_index = 0

    while start < len(cleaned):
        end = min(start + chunk_size, len(cleaned))
        if end < len(cleaned):
            split_at = cleaned.rfind(" ", start, end + 1)
            if split_at > start:
                end = split_at

        content = cleaned[start:end].strip()

        if content:
            chunks.append(ChunkData(chunk_index=chunk_index, content=content))
            chunk_index += 1

        start = end
        while start < len(cleaned) and cleaned[start] == " ":
            start += 1

    return chunks
