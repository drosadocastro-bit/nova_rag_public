#!/usr/bin/env python
"""Extract and analyze FAA documents."""

import pdfplumber

print("=" * 80)
print("FAA ARTIFICIAL INTELLIGENCE STRATEGY (March 2025)")
print("=" * 80)

# Extract FAA AI Strategy
with pdfplumber.open(r'C:\faa\faa-artificial-intelligence-strategy.pdf') as pdf:
    print(f"\nTotal Pages: {len(pdf.pages)}")
    print("\nExtracting key sections...\n")
    
    full_text = ""
    for i in range(min(15, len(pdf.pages))):
        text = pdf.pages[i].extract_text()
        if text:
            full_text += text + "\n\n"
    
    print(full_text[:8000])

print("\n\n" + "=" * 80)
print("Second Document: 82891.pdf")
print("=" * 80)

try:
    with pdfplumber.open(r'C:\faa\82891.pdf') as pdf:
        print(f"\nTotal Pages: {len(pdf.pages)}")
        for i in range(min(8, len(pdf.pages))):
            text = pdf.pages[i].extract_text()
            if text:
                print(f'\n--- Page {i+1} ---')
                print(text[:1500])
except Exception as e:
    print(f"Error: {e}")
