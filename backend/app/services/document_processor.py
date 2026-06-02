from __future__ import annotations

import hashlib
import re
from collections import Counter
from pathlib import Path


CHUNK_SIZE = 800
CHUNK_OVERLAP = 100


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(lines)
    return text.strip()


def deduplicate_chunks(chunks: list[str]) -> list[str]:
    """Remove near-duplicate chunks using content hash."""
    seen = set()
    unique = []
    for chunk in chunks:
        h = hashlib.sha256(chunk.encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(chunk)
    return unique


def chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries."""
    paragraphs = text.split("\n\n")
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) + 2 <= chunk_size:
            current = (current + "\n\n" + para).strip() if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[。！？.!?])\s*", para)
                sub = ""
                for sent in sentences:
                    sent = sent.strip()
                    if not sent:
                        continue
                    if len(sub) + len(sent) <= chunk_size:
                        sub = (sub + " " + sent).strip() if sub else sent
                    else:
                        if sub:
                            chunks.append(sub)
                        sub = sent
                if sub:
                    chunks.append(sub)
            else:
                current = para

    if current:
        chunks.append(current)

    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev = chunks[i - 1]
            curr = chunks[i]
            if len(prev) > overlap:
                tail = prev[-overlap:]
                if tail not in curr:
                    curr = tail + " " + curr
            overlapped.append(curr)
        chunks = overlapped

    return chunks


def parse_file_content(content: bytes, filename: str) -> tuple[str, str]:
    """Parse file content and return (text, content_type)."""
    ext = Path(filename).suffix.lower()

    if ext in (".txt", ".md", ".markdown"):
        return content.decode("utf-8", errors="replace"), "text/plain"
    elif ext == ".json":
        import json
        text = content.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
            if isinstance(data, list):
                text = "\n\n".join(
                    json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
                    for item in data
                )
            elif isinstance(data, dict):
                text = json.dumps(data, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass
        return text, "application/json"
    elif ext == ".csv":
        text = content.decode("utf-8", errors="replace")
        return text, "text/csv"
    else:
        text = content.decode("utf-8", errors="replace")
        return text, "application/octet-stream"


def _tokenize(text: str) -> Counter:
    """Tokenize text into weighted features for scoring.

    Chinese: character unigrams + bigrams.
    English/other: lowercased words + character bigrams.
    """
    features = Counter()

    # Chinese character bigrams
    cjk_chars = "".join(re.findall(r"[一-鿿㐀-䶿]", text))
    for i in range(len(cjk_chars)):
        features[cjk_chars[i]] += 2  # unigram weight
        if i < len(cjk_chars) - 1:
            features[cjk_chars[i:i + 2]] += 3  # bigram weight

    # English / mixed words
    word_matches = re.findall(r"[a-zA-Z0-9]{2,}", text)
    for w in word_matches:
        features[w.lower()] += 2

    # All character bigrams (catches mixed-language patterns)
    clean = re.sub(r"\s+", "", text)
    for i in range(len(clean) - 1):
        pair = clean[i:i + 2]
        features[pair] += 1

    return features


def search_chunks_local(
    query: str,
    chunks: list[str],
    top_k: int = 5,
) -> list[dict]:
    """Search chunks using n-gram / keyword overlap scoring.

    Returns top_k chunks with scores. Pure Python, no external dependencies.
    """
    if not chunks:
        return []

    query_features = _tokenize(query)
    if not query_features:
        return [{"content": c, "score": 0.0} for c in chunks[:top_k]]

    # Pre-compute chunk features
    chunk_features = [_tokenize(c) for c in chunks]

    # Score: intersection / union weighted by feature frequency
    scores = []
    for i, cf in enumerate(chunk_features):
        intersection = 0
        for feat, q_weight in query_features.items():
            if feat in cf:
                intersection += min(q_weight, cf[feat])
        union = sum(query_features.values()) + sum(cf.values()) - intersection
        score = intersection / union if union > 0 else 0.0
        scores.append((i, score, chunks[i]))

    scores.sort(key=lambda x: x[1], reverse=True)
    top = scores[:top_k]

    return [{"content": s[2], "score": s[1]} for s in top]
