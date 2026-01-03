"""
Quick verification script to check for legacy/sensitive references
Run this to verify the cleanup was successful
"""

import os
import re
from pathlib import Path

def check_file(filepath, patterns):
    """Check a file for specific patterns and return matches."""
    matches = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            for pattern_name, pattern in patterns.items():
                if re.search(pattern, content, re.IGNORECASE):
                    count = len(re.findall(pattern, content, re.IGNORECASE))
                    matches.append((pattern_name, count))
    except Exception as e:
        pass
    return matches

def main():
    print("="*60)
    print("NIC PUBLIC - CLEANUP VERIFICATION")
    print("="*60)
    print()
    
    # Patterns to check for
    patterns = {
        "Old Path (C:\\nova_rag)": r"C:\\nova_rag[^_]",
        "Nova Reyes": r"Nova Reyes",
        "Danny (technician)": r"\bDanny\b",
        "STALO": r"\bSTALO\b|\bstalo\b",
        "Klystron": r"\bklystron\b",
        "RDA/RPG": r"\bRDA\b|\bRPG\b",
        "Alarm Code (old)": r"ALARM_CODE|alarm_code|detect_alarm",
    }
    
    # Files to check (core application files only)
    files_to_check = [
        "backend.py",
        "nova_flask_app.py",
        "templates/index.html",
        "static/app.js",
        "static/style.css",
    ]
    
    base_dir = Path(__file__).parent
    issues_found = False
    
    for filename in files_to_check:
        filepath = base_dir / filename
        if not filepath.exists():
            print(f"⚠️  {filename} - File not found")
            continue
            
        matches = check_file(filepath, patterns)
        if matches:
            issues_found = True
            print(f"⚠️  {filename}:")
            for pattern_name, count in matches:
                print(f"    - {pattern_name}: {count} occurrence(s)")
        else:
            print(f"✅ {filename} - Clean")
    
    print()
    print("="*60)
    
    # Check for correct new paths
    print("\nVERIFYING CORRECT PATHS:")
    print("-"*60)
    
    backend_path = base_dir / "backend.py"
    if backend_path.exists():
        with open(backend_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'C:\\\\nova_rag_public' in content:
                print("✅ backend.py uses C:\\nova_rag_public")
            else:
                print("❌ backend.py missing C:\\nova_rag_public reference")
                
            if 'vehicle_index.faiss' in content:
                print("✅ backend.py uses vehicle_index.faiss")
            else:
                print("❌ backend.py missing vehicle_index.faiss reference")
                
            if 'ERROR_CODE_TO_DOCS' in content:
                print("✅ backend.py uses ERROR_CODE_TO_DOCS (not ALARM_CODE)")
            else:
                print("❌ backend.py missing ERROR_CODE_TO_DOCS")
    
    flask_path = base_dir / "nova_flask_app.py"
    if flask_path.exists():
        with open(flask_path, 'r', encoding='utf-8') as f:
            content = f.read()
            if 'C:\\\\nova_rag_public' in content:
                print("✅ nova_flask_app.py uses C:\\nova_rag_public")
            else:
                print("❌ nova_flask_app.py missing C:\\nova_rag_public reference")
    
    print()
    print("="*60)
    if not issues_found:
        print("✅ VERIFICATION PASSED - No sensitive references found")
        print("✅ All core files are clean and ready for public release")
    else:
        print("⚠️  ISSUES FOUND - Review warnings above")
        print("    Note: Some references in agents/ folder are expected")
        print("          (agents are not used in main Flask app)")
    print("="*60)

if __name__ == "__main__":
    main()
