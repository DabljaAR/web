"""NMT length adjuster — syllable-based Arabic text length adjustment via Groq.

Adjusts translated Arabic text to match the approximate phonetic length of the
original English source, keeping dubbing in sync with the audio timeline.
"""
import logging
import re

logger = logging.getLogger(__name__)

# ── Syllable / letter counters ───────────────────────────────────────────────


def count_en_syllables(text: str) -> int:
    """Approximate English syllable count via vowel-cluster heuristic."""
    text = text.lower()
    text = re.sub(r"[^a-z\s]", "", text)
    count = 0
    for word in text.split():
        vowels = re.findall(r"[aeiouy]+", word)
        count += max(1, len(vowels))
    return count


def count_ar_syllables(text: str) -> int:
    """Arabic 'syllable' proxy: count of Arabic letter codepoints (diacritics stripped)."""
    text = re.sub(r"[\u064B-\u065F]", "", text)
    return len(re.findall(r"[\u0621-\u064A]", text))


# ── Groq rewrite helper ──────────────────────────────────────────────────────


def _rewrite_ar(client, model: str, text: str, percent: int, mode: str) -> str:
    """Single Groq rewrite call. Returns original text on any failure."""
    if mode == "shorten":
        instruction = (
            f"Rewrite the sentence to be approximately {percent}% shorter "
            "in speaking length while preserving the exact original meaning."
        )
    else:
        instruction = (
            f"Rewrite the sentence to be approximately {percent}% longer "
            "in speaking length while preserving the exact original meaning."
        )

    prompt = f"""{instruction}

STRICT REQUIREMENTS:
- Preserve the exact meaning. Do not change, remove, or distort any important information.
- Do NOT introduce any new information or facts.
- If needed, you may add or remove minor natural filler words only to meet the length requirement.
- The output MUST be in Modern Standard Arabic (MSA) only.
- Return EXACTLY one complete sentence.
- Do NOT include any explanation, commentary, or extra text.
- Do NOT output lists, multiple sentences, or fragments.
- Ensure the sentence is grammatically correct and natural.
- Ensure the sentence is fully complete (not cut or truncated).
- Do NOT repeat words or phrases. Every added word must carry meaning.

Sentence:
{text}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        result = response.choices[0].message.content.strip()
        return result if result else text
    except Exception as exc:
        logger.warning("[NMT][adjust] Groq rewrite failed: %s", exc)
        return text


# ── Public API ───────────────────────────────────────────────────────────────


def adjust_ar(
    ar_text: str,
    en_text: str,
    *,
    scale: float,
    max_iters: int,
    groq_api_key: str,
    groq_model: str,
) -> str:
    """Iteratively rewrite *ar_text* until its Arabic-letter count approximates
    ``count_en_syllables(en_text) * scale``, within a tolerance of ±2 letters.

    Returns *ar_text* unchanged when:
    - ``groq_api_key`` is empty (Groq not configured)
    - the ``groq`` package is not installed
    - any exception prevents adjustment (graceful fallback)
    """
    if not groq_api_key:
        logger.debug("[NMT][adjust] GROQ_API_KEY not set — skipping length adjustment")
        return ar_text

    if not ar_text or not en_text:
        return ar_text

    try:
        from groq import Groq  # lazy import — not required at module load time
        client = Groq(api_key=groq_api_key)
    except ImportError:
        logger.warning("[NMT][adjust] groq package not installed — skipping length adjustment")
        return ar_text
    except Exception as exc:
        logger.warning("[NMT][adjust] Failed to create Groq client: %s", exc)
        return ar_text

    en_syllables = count_en_syllables(en_text)
    target = int(en_syllables * scale)

    if target <= 0:
        return ar_text

    initial_ar_count = count_ar_syllables(ar_text)
    current_text = ar_text

    for iteration in range(max_iters):
        current = count_ar_syllables(current_text)
        if abs(current - target) <= 2:
            break
        if current > target:
            percent = max(10, min(int((current - target) / current * 100), 20))
            current_text = _rewrite_ar(client, groq_model, current_text, percent, "shorten")
        else:
            percent = max(10, min(int((target - current) / max(current, 1) * 100), 20))
            current_text = _rewrite_ar(client, groq_model, current_text, percent, "expand")

        logger.debug(
            "[NMT][adjust] iter=%d current_ar=%d target=%d",
            iteration + 1, count_ar_syllables(current_text), target,
        )

    logger.info(
        "[NMT][adjust] en_syllables=%d target_ar=%d initial_ar=%d final_ar=%d",
        en_syllables, target, initial_ar_count, count_ar_syllables(current_text),
    )
    return current_text
