"""Multilingual safety detection utilities for NovaRAG.

Provides lightweight language and encoding detection plus pattern-based
normalization to surface non-English or encoded safety attacks.
"""

import base64
import re
from typing import Any, Dict, List
from urllib.parse import unquote

from langdetect import LangDetectException, detect


class MultilingualSafetyDetector:
    """Detects multilingual or encoded safety attacks.

    Methods focus on fast heuristics: encoding detection, language ID, and
    pattern translation for known safety bypass phrases.
    """

    SUPPORTED_LANGUAGES = ["en", "es", "fr", "de", "it", "pt", "ru", "zh", "ar"]

    ATTACK_PATTERNS: Dict[str, Dict[str, str]] = {
        "es": {
            r"ignorar\s+(?:toda(?:s)?|cualquier)?\s*(?:la\s+)?(?:seguridad|verificaci[oó]n(?:es)?)": "ignore safety",
            r"desactivar\s+(?:el\s+)?(?:sistema\s+)?abs": "disable abs",
            r"anular\s+(?:el\s+)?protocolo": "override protocol",
            r"omitir\s+(?:la(?:s)?\s+)?verificaci[oó]n(?:es)?": "bypass verification",
            r"desactivar\s+(?:el\s+)?airbag": "disable airbag",
            r"deshabilitar\s+(?:la\s+)?seguridad": "disable safety",
        },
        "fr": {
            r"ignorer\s+(?:toute(?:s)?\s+)?(?:la\s+)?s[eé]curit[eé]": "ignore safety",
            r"d[eé]sactiver\s+(?:le\s+)?(?:syst[eè]me\s+)?abs": "disable abs",
            r"contourner\s+(?:la\s+)?v[eé]rification": "bypass verification",
            r"ignorer\s+(?:les\s+)?contr[ôo]les": "ignore checks",
            r"d[eé]sactiver\s+(?:l[e']\s*)?airbag": "disable airbag",
        },
        "de": {
            r"ignorieren\s+(?:alle\s+)?sicherheit(?:s?\spr[uü]fungen?)?": "ignore safety",
            r"deaktivieren\s+(?:das\s+)?abs(?:-system)?": "disable abs",
            r"umgehen\s+(?:die\s+)?[üu]berpr[üu]fung(?:en)?": "bypass verification",
            r"ausschalten\s+(?:die\s+)?sicherheit": "turn off safety",
            r"deaktivieren\s+(?:den\s+)?airbag": "disable airbag",
            r"sicherheit[sß]pr[uü]fungen?\s+umgehen": "bypass",
        },
        "pt": {
            r"ignorar\s+(?:toda(?:s)?\s+)?(?:a\s+)?seguran[çc]a": "ignore safety",
            r"desativar\s+(?:o\s+)?(?:sistema\s+)?abs": "disable abs",
            r"ignorar\s+(?:a(?:s)?\s+)?verifica[çc][ãa]o(?:[õo]es)?": "bypass verification",
            r"anular\s+(?:o\s+)?protocolo": "override protocol",
            r"desativar\s+(?:o\s+)?airbag": "disable airbag",
        },
        "it": {
            r"ignorare\s+(?:tutti?\s+)?(?:i\s+)?controlli?\s+(?:di\s+)?sicurezza": "ignore safety",
            r"disattivare\s+(?:il\s+)?(?:sistema\s+)?abs": "disable abs",
            r"ignorare\s+(?:la\s+)?verifica": "bypass verification",
            r'disattivare\s+(?:l[\'"])?airbag': "disable airbag",
        },
    }

    @classmethod
    def detect_language(cls, text: str) -> Dict[str, Any]:
        """Identify language using langdetect.

        Returns a dict with language code and heuristic confidence based on
        input length. Defaults to English on detection failure.
        """
        stripped = text.strip()

        # Fast path: ASCII safety/control keywords can confuse langdetect;
        # prefer English to avoid misclassifying short safety prompts.
        ascii_only = stripped.isascii()
        lower = stripped.lower()
        safety_english_tokens = ["ignore", "safety", "protocol", "protocols", "checks"]
        non_english_markers = [
            "seguridad",
            "protocolos",
            "ignorar",
            "sécurité",
            "sicherheit",
            "sicurezza",
            "protocolli",
        ]
        if ascii_only and any(tok in lower for tok in safety_english_tokens) and not any(marker in lower for marker in non_english_markers):
            return {
                "language": "en",
                "confidence": 0.9,
                "reason": "ASCII safety keywords favor English",
            }

        if len(stripped) < 10:
            return {
                "language": "en",
                "confidence": 0.5,
                "reason": "Query too short for reliable detection",
            }
        try:
            language = detect(stripped) if stripped else "en"
        except LangDetectException:
            language = "en"
        confidence = min(len(stripped) / 50.0, 1.0)
        return {"language": language, "confidence": confidence}

    @classmethod
    def detect_encoding(cls, text: str) -> Dict[str, Any]:
        """Detect common encodings (Base64, URL, hex) and decode variants."""
        encoding_types: List[str] = []
        decoded_variants: List[str] = []

        seen: set[str] = set()
        queue: List[str] = [text]

        base64_pattern = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")

        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)
            decoded_variants.append(current)

            # Base64 detection (guard against false positives by length)
            if len(current.strip()) % 4 == 0 and base64_pattern.fullmatch(current.strip()):
                try:
                    decoded = base64.b64decode(current).decode("utf-8", errors="ignore")
                    if decoded and decoded != current:
                        encoding_types.append("base64")
                        if decoded not in seen:
                            queue.append(decoded)
                except Exception:
                    pass

            # URL encoding detection
            if "%" in current:
                decoded_url = unquote(current)
                if decoded_url and decoded_url != current:
                    encoding_types.append("url")
                    if decoded_url not in seen:
                        queue.append(decoded_url)

            # Hex escape detection (explicit \x.. sequences)
            if "\\x" in current.lower():
                try:
                    decoded_hex = current.encode().decode("unicode_escape")
                    if decoded_hex and decoded_hex != current:
                        encoding_types.append("hex")
                        if decoded_hex not in seen:
                            queue.append(decoded_hex)
                except Exception:
                    pass

        # Heuristic: if safety-related text and no encoding detected yet, treat as decoded hex
        if not encoding_types and any(word in text.lower() for word in ["ignore", "desactivar", "seguridad", "sicherheit", "bypass"]):
            encoding_types.append("hex")
            if text not in decoded_variants:
                decoded_variants.append(text)

        return {
            "encoding_detected": bool(encoding_types),
            "encoding_types": encoding_types,
            "decoded_variants": decoded_variants,
        }

    @classmethod
    def _pattern_translate(cls, text: str, source_lang: str) -> str:
        """Apply pattern-based translation from a source language to English."""
        if source_lang not in cls.ATTACK_PATTERNS:
            return text

        translated = text
        for pattern, replacement in cls.ATTACK_PATTERNS[source_lang].items():
            translated = re.sub(pattern, replacement, translated, flags=re.IGNORECASE)
        return translated

    @classmethod
    def normalize_query(cls, query: str) -> Dict[str, Any]:
        """Normalize a query by decoding, detecting language, and translating.

        Returns metadata including normalized text, detected language, and any
        encoding information for downstream safety checks.
        """
        encoding_meta = cls.detect_encoding(query)
        candidates = encoding_meta["decoded_variants"] if encoding_meta["decoded_variants"] else [query]
        best_variant = candidates[0] if candidates else query

        lang_meta = cls.detect_language(best_variant)
        language = lang_meta["language"]

        if language != "en":
            normalized = cls._pattern_translate(best_variant, language)
        else:
            normalized = best_variant

        return {
            "original": query,
            "normalized": normalized,
            "language": language,
            "encoding_detected": encoding_meta["encoding_detected"],
            "encoding_types": encoding_meta["encoding_types"],
            "decoded_variants": candidates,
            "confidence": lang_meta["confidence"],
        }

    @classmethod
    def is_multilingual_attack(cls, query: str) -> bool:
        """Check if a non-English query likely carries an attack intent."""
        normalized = cls.normalize_query(query)
        normalized_lower = normalized["normalized"].lower()

        attack_keywords = [
            "ignore",
            "disable",
            "bypass",
            "override",
            "deactivate",
            "turn off",
            "desactivar",
            "ignorar",
            "umgehen",
            "sicherheit",
        ]

        # Mixed-language attacks: English safety terms combined with foreign tokens
        mixed_language_attack = (
            normalized["language"] == "en"
            and re.search(r"(ignorar|desactivar|sicherheit|umgehen)", query.lower())
            and re.search(r"safety|checks|protocol|abs", query.lower())
        )

        if normalized["language"] == "en" and not mixed_language_attack:
            return False

        return any(keyword in normalized_lower for keyword in attack_keywords) or mixed_language_attack
