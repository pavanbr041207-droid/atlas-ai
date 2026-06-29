"""
services/document_intelligence.py
Profile documents: PDF, DOCX, PPTX, TXT, MD.
Generate metadata, summary, keywords, headings, retrieval chunks.
"""
import re
import os

STOP = {
    "the","a","an","and","or","but","in","on","at","to","for","of","with",
    "by","from","is","was","are","were","be","been","have","has","had","this",
    "that","these","those","it","its","we","our","they","their","i","my","you",
    "your","he","she","his","her","not","no","as","so","if","then","than",
    "into","up","out","about","over","after","before","will","would","could",
    "should","may","might","can","do","does","did","which","who","when","where",
}


def profile_document(file_path: str, filename: str, file_id: str,
                     doc_type: str, text_content: str = "") -> dict:
    """
    Generate comprehensive document profile.
    Returns: {title, filename, type, chars, words, headings, keywords,
              entities, summary, chunks, chunk_count}
    """
    if not text_content:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text_content = f.read()
        except Exception:
            text_content = ""

    if not text_content:
        return {
            "title":       os.path.splitext(filename)[0],
            "filename":    filename,
            "type":        doc_type,
            "chars":       0,
            "words":       0,
            "chunks":      [],
            "keywords":    [],
            "headings":    [],
            "summary":     "",
            "chunk_count": 0,
        }

    title    = _extract_title(text_content, filename)
    headings = _extract_headings(text_content)
    keywords = _extract_keywords(text_content)
    entities = _extract_entities(text_content)
    summary  = _extract_summary(text_content)
    chunks   = _chunk_text(text_content, file_id, filename)

    return {
        "title":       title,
        "filename":    filename,
        "type":        doc_type,
        "chars":       len(text_content),
        "words":       len(text_content.split()),
        "headings":    headings[:10],
        "keywords":    keywords[:15],
        "entities":    entities[:20],
        "summary":     summary,
        "chunks":      chunks,
        "chunk_count": len(chunks),
    }


def _extract_title(text: str, filename: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if lines:
        first = lines[0]
        if len(first) < 120 and not first.endswith("."):
            return first
    stem = os.path.splitext(filename)[0]
    return stem.replace("_", " ").replace("-", " ").title()


def _extract_headings(text: str) -> list:
    headings = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            h = re.sub(r"^#+\s*", "", line).strip()
            if h:
                headings.append(h)
        elif line.isupper() and 3 < len(line) < 80:
            headings.append(line.title())
        elif re.match(r"^\d+[\.\)]\s+[A-Z]", line) and len(line) < 100:
            headings.append(line)
    return list(dict.fromkeys(headings))


def _extract_keywords(text: str, top_n: int = 15) -> list:
    words = re.findall(r"\b[a-zA-Z]{4,}\b", text.lower())
    freq  = {}
    for w in words:
        if w not in STOP:
            freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: x[1], reverse=True)[:top_n]]


def _extract_entities(text: str) -> list:
    entities = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b", text)
    seen, result = set(), []
    for e in entities:
        if e not in seen and len(e) > 5:
            seen.add(e)
            result.append(e)
    return result[:20]


def _extract_summary(text: str, max_chars: int = 500) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    for p in paragraphs:
        if len(p) > 50:
            return p[:max_chars]
    return text[:max_chars]


def _chunk_text(text: str, file_id: str, filename: str,
                chunk_size: int = 600, overlap: int = 100) -> list:
    """Split text into overlapping chunks for retrieval."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks, current, current_len, idx = [], [], 0, 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        current.append(sentence)
        current_len += len(sentence)

        if current_len >= chunk_size:
            chunks.append({
                "chunk_id": f"{file_id}_{idx}",
                "file_id":  file_id,
                "filename": filename,
                "text":     " ".join(current),
                "index":    idx,
            })
            idx += 1
            # Keep last few sentences as overlap
            overlap_sents, overlap_len = [], 0
            for s in reversed(current):
                if overlap_len + len(s) < overlap * 4:
                    overlap_sents.insert(0, s)
                    overlap_len += len(s)
                else:
                    break
            current, current_len = overlap_sents, overlap_len

    if current:
        chunks.append({
            "chunk_id": f"{file_id}_{idx}",
            "file_id":  file_id,
            "filename": filename,
            "text":     " ".join(current),
            "index":    idx,
        })
    return chunks
