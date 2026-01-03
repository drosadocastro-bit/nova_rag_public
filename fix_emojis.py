#!/usr/bin/env python3
"""Remove all Unicode emojis from agent_router.py"""

import re

file_path = r'c:\nova_rag_public\agents\agent_router.py'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace emojis with text
replacements = {
    '⚠️': '[WARNING]',
    '❌': '[ERROR]',
    '✓': '[OK]',
    '📊': '[METRICS]',
    '🚧': '[BUILDING]',
    '💡': '[TIP]',
    '↪': '->',
    '→': '->',
    '⚡': '[POWER]',
    '🔧': '[TOOL]',
}

for emoji, text in replacements.items():
    if emoji in content:
        content = content.replace(emoji, text)
        print(f"Replaced '{emoji}' with '{text}'")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Done!")
