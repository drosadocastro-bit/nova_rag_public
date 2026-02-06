"""
Post-Generation Output Sanitizer - LLM02 Defense

This module provides deterministic, post-generation sanitization of LLM output.
The LLM cannot be trusted to self-sanitize, so this layer is applied AFTER generation.

Defenses against:
- XSS via script tags
- HTML injection
- JavaScript injection  
- Data URL attacks
- Event handler injection

Reference: OWASP LLM02 - Insecure Output Handling
"""

from __future__ import annotations

import re
import html
import logging
from typing import Tuple, List, Dict, Any

logger = logging.getLogger(__name__)

# =========================================================
# BLOCKED PATTERNS - Never allowed in output
# =========================================================

# Script and execution vectors
BLOCKED_PATTERNS = [
    # Script tags (with variations)
    (r'<\s*script[^>]*>.*?</\s*script\s*>', ''),
    (r'<\s*script[^>]*/?>', ''),
    
    # Iframe injection
    (r'<\s*iframe[^>]*>.*?</\s*iframe\s*>', '[blocked: iframe]'),
    (r'<\s*iframe[^>]*/?>', '[blocked: iframe]'),
    
    # Object/embed (Flash, plugins)
    (r'<\s*object[^>]*>.*?</\s*object\s*>', '[blocked: object]'),
    (r'<\s*embed[^>]*/?>', '[blocked: embed]'),
    
    # Base tag (URL hijacking)
    (r'<\s*base[^>]*/?>', '[blocked: base]'),
    
    # Form actions (phishing)
    (r'<\s*form[^>]*>.*?</\s*form\s*>', '[blocked: form]'),
    
    # Meta refresh (redirect)
    (r'<\s*meta[^>]*http-equiv\s*=\s*["\']?refresh[^>]*/?>', '[blocked: meta-refresh]'),
    
    # Link with import
    (r'<\s*link[^>]*rel\s*=\s*["\']?import[^>]*/?>', '[blocked: link-import]'),
]

# Event handlers (onload, onclick, onerror, etc.)
EVENT_HANDLER_PATTERN = re.compile(
    r'\s+on\w+\s*=\s*["\'][^"\']*["\']',
    re.IGNORECASE
)

# JavaScript URLs
JS_URL_PATTERNS = [
    re.compile(r'javascript\s*:', re.IGNORECASE),
    re.compile(r'vbscript\s*:', re.IGNORECASE),
    re.compile(r'data\s*:\s*text/html', re.IGNORECASE),
    re.compile(r'data\s*:\s*application/javascript', re.IGNORECASE),
]

# Dangerous CSS
CSS_EXPRESSION_PATTERN = re.compile(
    r'expression\s*\(',
    re.IGNORECASE
)

# =========================================================
# ALLOWED HTML TAGS (Allowlist approach)
# =========================================================

# Tags safe for markdown-style rendering
ALLOWED_TAGS = {
    'p', 'br', 'hr',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'strong', 'b', 'em', 'i', 'u', 's', 'strike',
    'ul', 'ol', 'li',
    'blockquote', 'pre', 'code',
    'table', 'thead', 'tbody', 'tr', 'th', 'td',
    'sup', 'sub',
}

# Allowed attributes (very restricted)
ALLOWED_ATTRS = {
    'class',  # For styling only
    'id',     # For anchors only  
}

# Citation-related patterns that should preserve < >
CITATION_PATTERNS = [
    re.compile(r'\[Source:\s*[^\]]+\]'),
    re.compile(r'\[Page\s+\d+\]'),
    re.compile(r'\[Ref:\s*[^\]]+\]'),
    re.compile(r'\[Citation:\s*[^\]]+\]'),
]

# =========================================================
# COMPILED PATTERNS
# =========================================================

_BLOCKED_COMPILED = [(re.compile(p, re.IGNORECASE | re.DOTALL), r) for p, r in BLOCKED_PATTERNS]


def sanitize_output(text: str, allow_markdown: bool = True) -> Tuple[str, Dict[str, Any]]:
    """
    Sanitize LLM output to prevent XSS and HTML injection.
    
    This is a DETERMINISTIC post-generation filter. The LLM cannot be trusted
    to self-sanitize, so this layer must be applied.
    
    Args:
        text: Raw LLM output text
        allow_markdown: If True, preserve markdown formatting. If False, escape everything.
    
    Returns:
        Tuple of (sanitized_text, metadata)
        - sanitized_text: Safe output
        - metadata: Dict with 'blocked_count', 'blocked_types', 'was_modified'
    """
    if not text or not isinstance(text, str):
        return str(text) if text else "", {"blocked_count": 0, "blocked_types": [], "was_modified": False}
    
    original = text
    blocked_types: List[str] = []
    blocked_count = 0
    
    # Phase 1: Remove explicitly blocked patterns
    for pattern, replacement in _BLOCKED_COMPILED:
        matches = pattern.findall(text)
        if matches:
            blocked_count += len(matches)
            # Determine type from pattern
            if 'script' in pattern.pattern.lower():
                blocked_types.append('script')
            elif 'iframe' in pattern.pattern.lower():
                blocked_types.append('iframe')
            elif 'object' in pattern.pattern.lower() or 'embed' in pattern.pattern.lower():
                blocked_types.append('object/embed')
            elif 'form' in pattern.pattern.lower():
                blocked_types.append('form')
            elif 'meta' in pattern.pattern.lower():
                blocked_types.append('meta-refresh')
            else:
                blocked_types.append('html-tag')
            text = pattern.sub(replacement, text)
    
    # Phase 2: Remove event handlers (onload=, onclick=, onerror=, etc.)
    event_matches = EVENT_HANDLER_PATTERN.findall(text)
    if event_matches:
        blocked_count += len(event_matches)
        blocked_types.append('event-handler')
        text = EVENT_HANDLER_PATTERN.sub('', text)
    
    # Phase 3: Neutralize JavaScript/data URLs
    for js_pattern in JS_URL_PATTERNS:
        if js_pattern.search(text):
            blocked_count += 1
            blocked_types.append('javascript-url')
            text = js_pattern.sub('[blocked-url]', text)
    
    # Phase 4: Remove CSS expressions
    if CSS_EXPRESSION_PATTERN.search(text):
        blocked_count += 1
        blocked_types.append('css-expression')
        text = CSS_EXPRESSION_PATTERN.sub('[blocked-expression]', text)
    
    # Phase 5: Handle remaining HTML tags
    if not allow_markdown:
        # Escape everything
        text = html.escape(text)
    else:
        # Selective escaping: keep allowed tags, escape others
        text = _sanitize_html_tags(text)
    
    # Log if anything was blocked
    was_modified = text != original
    if blocked_count > 0:
        logger.warning(
            f"[OUTPUT_SANITIZER] Blocked {blocked_count} dangerous patterns: {set(blocked_types)}"
        )
    
    return text, {
        "blocked_count": blocked_count,
        "blocked_types": list(set(blocked_types)),
        "was_modified": was_modified,
    }


def _sanitize_html_tags(text: str) -> str:
    """
    Sanitize HTML tags while preserving allowed formatting tags.
    
    Uses an allowlist approach - only explicitly allowed tags pass through.
    All other < > are escaped.
    """
    # Regex to find all HTML-like tags
    tag_pattern = re.compile(r'<(/?)(\w+)([^>]*)>')
    
    def replace_tag(match: re.Match) -> str:
        closing = match.group(1)
        tag_name = match.group(2).lower()
        attrs = match.group(3)
        
        if tag_name in ALLOWED_TAGS:
            # Filter attributes to only allowed ones
            safe_attrs = _filter_attributes(attrs)
            if closing:
                return f'</{tag_name}>'
            elif safe_attrs:
                return f'<{tag_name}{safe_attrs}>'
            else:
                return f'<{tag_name}>'
        else:
            # Escape the tag
            return html.escape(match.group(0))
    
    return tag_pattern.sub(replace_tag, text)


def _filter_attributes(attrs: str) -> str:
    """Filter attributes to only allowed safe ones."""
    if not attrs or not attrs.strip():
        return ""
    
    # Parse attributes
    attr_pattern = re.compile(r'(\w+)\s*=\s*["\']([^"\']*)["\']')
    safe_parts = []
    
    for match in attr_pattern.finditer(attrs):
        attr_name = match.group(1).lower()
        attr_value = match.group(2)
        
        # Only allow safe attributes
        if attr_name in ALLOWED_ATTRS:
            # Escape the value
            safe_value = html.escape(attr_value)
            safe_parts.append(f'{attr_name}="{safe_value}"')
    
    return ' ' + ' '.join(safe_parts) if safe_parts else ""


def strip_all_html(text: str) -> str:
    """
    Completely strip all HTML tags from text.
    
    Use this for maximum safety when HTML is not needed.
    """
    # First, remove blocked patterns
    for pattern, _ in _BLOCKED_COMPILED:
        text = pattern.sub('', text)
    
    # Then strip all remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    
    return text


def escape_for_json(text: str) -> str:
    """
    Escape text for safe JSON embedding.
    
    Prevents JSON injection attacks.
    """
    # Standard escapes
    text = text.replace('\\', '\\\\')
    text = text.replace('"', '\\"')
    text = text.replace('\n', '\\n')
    text = text.replace('\r', '\\r')
    text = text.replace('\t', '\\t')
    
    # Additional safety: escape </script> to prevent breaking out of JSON in script tags
    text = text.replace('</script>', '<\\/script>')
    text = text.replace('</Script>', '<\\/Script>')
    text = text.replace('</SCRIPT>', '<\\/SCRIPT>')
    
    return text


# =========================================================
# CONVENIENCE WRAPPER
# =========================================================

def sanitize_llm_output(text: str) -> str:
    """
    Simple wrapper that sanitizes and returns only the text.
    
    Use this for quick sanitization without metadata.
    """
    sanitized, _ = sanitize_output(text, allow_markdown=True)
    return sanitized


# =========================================================
# MODULE EXPORTS
# =========================================================

__all__ = [
    "sanitize_output",
    "sanitize_llm_output",
    "strip_all_html",
    "escape_for_json",
    "ALLOWED_TAGS",
    "BLOCKED_PATTERNS",
]
