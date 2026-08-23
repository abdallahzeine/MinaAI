"""Text batching and sentence splitting module for Audar TTS.

Splits input text into natural sentence/separator batches while guaranteeing
that English statements are never sent alone to the Arabic-first Audar model
without surrounding Arabic context.
"""

from __future__ import annotations

import re
from typing import List

# Arabic unicode block regex pattern
ARABIC_PATTERN = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LATIN_PATTERN = re.compile(r"[a-zA-Z]")

# Expression tags supported by Audar
TAG_PATTERN = re.compile(r"\[(laughs|curious|excited|sighs|exhales|mischievously|whispers|sarcastic)\]", re.IGNORECASE)

# Split boundaries: sentence delimiters (. ! ? ؟ \n ؛) preserving tags
# Note: we avoid splitting inside brackets [...]
SENTENCE_SPLIT_REGEX = re.compile(r"(?<=[.!؟?\n؛])\s+(?![^\[]*\])")

# Default anchor used only when the entire prompt contains zero Arabic characters
DEFAULT_ARABIC_ANCHOR = "أهلاً بك، "


def has_arabic(text: str) -> bool:
    """Return True if the text contains at least one Arabic character."""
    return bool(ARABIC_PATTERN.search(text))


def has_latin(text: str) -> bool:
    """Return True if the text contains at least one Latin/English character."""
    return bool(LATIN_PATTERN.search(text))


def clean_text(text: str) -> str:
    """Clean markdown artifacts and extra whitespace while preserving expression tags."""
    if not text:
        return ""
    # Strip markdown headers, bold, italics, bullets
    t = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
    t = re.sub(r"\*([^*]+)\*", r"\1", t)
    t = re.sub(r"^[-*•]\s*", "", t, flags=re.MULTILINE)
    # Collapse consecutive whitespaces and newlines
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n\s*\n+", "\n", t)
    return t.strip()


def split_into_batches(
    text: str,
    max_chunk_chars: int = 180,
    min_chunk_chars: int = 20,
) -> List[str]:
    """Split text into sentence-level batches for synthesis.
    
    Guarantees:
    1. English statements are NEVER isolated — always surrounded or merged with Arabic text.
    2. Expression tags ([whispers], [laughs], etc.) are preserved in context.
    3. Chunks are sized naturally for optimal neural acoustic token prediction.
    """
    cleaned = clean_text(text)
    if not cleaned:
        return []

    # If the entire input has no Arabic characters at all, frame it with a natural Arabic anchor
    if not has_arabic(cleaned):
        cleaned = f"{DEFAULT_ARABIC_ANCHOR}{cleaned}"

    # Step 1: Initial split by sentence separators and newlines
    raw_segments: list[str] = []
    # First split on newlines
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    for line in lines:
        # Split on sentence boundaries (. ! ? ؟ ؛)
        parts = SENTENCE_SPLIT_REGEX.split(line)
        for p in parts:
            p_str = p.strip()
            if p_str:
                raw_segments.append(p_str)

    if not raw_segments:
        return []

    # Step 2: Merge isolated English / non-Arabic segments with adjacent Arabic segments
    merged_segments: list[str] = []
    for seg in raw_segments:
        if not has_arabic(seg):
            # Pure English / non-Arabic statement
            if merged_segments and has_arabic(merged_segments[-1]):
                # Merge with the preceding Arabic segment
                merged_segments[-1] = f"{merged_segments[-1]} {seg}"
            else:
                # No preceding Arabic segment yet; start a pending item
                merged_segments.append(seg)
        else:
            # Segment contains Arabic
            if merged_segments and not has_arabic(merged_segments[-1]):
                # Previous segment was pure English; merge it into this Arabic segment
                prev = merged_segments.pop()
                merged_segments.append(f"{prev} {seg}")
            else:
                merged_segments.append(seg)

    # Secondary pass: Ensure no segment in merged_segments is without Arabic
    final_arabic_safe: list[str] = []
    for seg in merged_segments:
        if not has_arabic(seg):
            if final_arabic_safe:
                final_arabic_safe[-1] = f"{final_arabic_safe[-1]} {seg}"
            else:
                final_arabic_safe.append(f"{DEFAULT_ARABIC_ANCHOR}{seg}")
        else:
            final_arabic_safe.append(seg)

    # Step 3: Size normalization (merge tiny chunks, split oversized chunks on commas)
    batches: list[str] = []
    current = ""

    for seg in final_arabic_safe:
        # If adding seg to current exceeds max_chunk_chars and current has reasonable length
        if current:
            combined = f"{current} {seg}".strip()
            if len(combined) <= max_chunk_chars:
                current = combined
                continue
            else:
                batches.append(current)
                current = seg
        else:
            current = seg

    if current:
        # If current is very short and we already have batches, merge into last batch
        if len(current) < min_chunk_chars and batches:
            batches[-1] = f"{batches[-1]} {current}".strip()
        else:
            batches.append(current)

    # Ensure every single batch has Arabic
    verified_batches: list[str] = []
    for b in batches:
        b_str = b.strip()
        if not b_str:
            continue
        if not has_arabic(b_str):
            b_str = f"{DEFAULT_ARABIC_ANCHOR}{b_str}"
        verified_batches.append(b_str)

    return verified_batches
