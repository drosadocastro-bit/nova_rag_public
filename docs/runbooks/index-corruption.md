# Runbook: Index Corruption / Recovery

## Symptoms
- "Index file corrupted" errors
- Retrieval returns empty results
- FAISS read errors
- BM25 pickle errors
- Inconsistent search results

---

## Quick Diagnosis

```bash
# Check index files exist
ls -la vector_db/

# Verify FAISS index
python -c "
import faiss
try:
    index = faiss.read_index('vector_db/faiss_index.bin')
    print(f'FAISS OK: {index.ntotal} vectors')
except Exception as e:
    print(f'FAISS ERROR: {e}')
"

# Verify BM25 index
python -c "
import pickle
try:
    with open('vector_db/bm25_index.pkl', 'rb') as f:
        bm25 = pickle.load(f)
    print(f'BM25 OK: {len(bm25.doc_len)} documents')
except Exception as e:
    print(f'BM25 ERROR: {e}')
"

# Check metadata
python -c "
import json
with open('vector_db/metadata.json', 'r') as f:
    meta = json.load(f)
print(f'Metadata: {len(meta)} entries')
"
```

---

## Issue: FAISS Index Corrupted

### Symptoms
```
RuntimeError: Error reading index from vector_db/faiss_index.bin
faiss.swigfaiss.SwigPyIterator: Unable to read index
```

### Diagnosis
```bash
# Check file integrity
file vector_db/faiss_index.bin
# Should show: "data" or "FAISS index"

# Check file size
ls -lh vector_db/faiss_index.bin
# Suspiciously small = likely corrupted
```

### Resolution

**Restore from backup:**
```bash
# Check for backups
ls -la vector_db/backups/

# Restore latest backup
cp vector_db/backups/faiss_index.bin.20260125 vector_db/faiss_index.bin
```

**Rebuild from source documents:**
```bash
# Full rebuild
python ingest_vehicle_manual.py --rebuild

# Or rebuild specific domain
python ingest_vehicle_manual.py --domain vehicle --rebuild
```

### Prevention
- Enable automatic backups before ingestion
- Monitor index file size in metrics

---

## Issue: BM25 Index Corrupted

### Symptoms
```
UnpicklingError: invalid load key
_pickle.UnpicklingError: could not find MARK
```

### Diagnosis
```bash
# Check file
file vector_db/bm25_index.pkl
# Should show: "data" or "Python pickle"

# Check size
ls -lh vector_db/bm25_index.pkl
```

### Resolution

**Restore from backup:**
```bash
cp vector_db/backups/bm25_index.pkl.20260125 vector_db/bm25_index.pkl
```

**Rebuild from documents:**
```bash
# BM25 is rebuilt during ingestion
python ingest_vehicle_manual.py --rebuild
```

### Prevention
- Backup before updates
- Use atomic writes during ingestion

---

## Issue: Metadata Mismatch

### Symptoms
- FAISS returns IDs not in metadata
- Missing chunk content
- "KeyError" when retrieving documents

### Diagnosis
```bash
# Count entries in each
python -c "
import faiss
import json
import pickle

index = faiss.read_index('vector_db/faiss_index.bin')
with open('vector_db/metadata.json') as f:
    meta = json.load(f)
with open('vector_db/bm25_index.pkl', 'rb') as f:
    bm25 = pickle.load(f)

print(f'FAISS vectors: {index.ntotal}')
print(f'Metadata entries: {len(meta)}')
print(f'BM25 documents: {len(bm25.doc_len)}')

if index.ntotal != len(meta):
    print('⚠ MISMATCH: FAISS and metadata out of sync!')
"
```

### Resolution

**Rebuild all indices:**
```bash
# Remove existing indices
rm -rf vector_db/*.bin vector_db/*.pkl vector_db/*.json

# Rebuild from scratch
python ingest_vehicle_manual.py --rebuild --all-domains
```

### Prevention
- Use atomic updates (write to temp, then rename)
- Verify counts after ingestion

---

## Issue: Index File Missing

### Symptoms
```
FileNotFoundError: [Errno 2] No such file or directory: 'vector_db/faiss_index.bin'
```

### Resolution

**Check for alternative locations:**
```bash
find . -name "*.bin" -o -name "*faiss*"
```

**Restore from backup:**
```bash
# List backups
ls -la vector_db/backups/

# Restore all index files
cp vector_db/backups/faiss_index.bin.latest vector_db/faiss_index.bin
cp vector_db/backups/bm25_index.pkl.latest vector_db/bm25_index.pkl
cp vector_db/backups/metadata.json.latest vector_db/metadata.json
```

**Rebuild if no backup:**
```bash
python ingest_vehicle_manual.py --rebuild
```

---

## Issue: Partial Index (Incomplete Ingestion)

### Symptoms
- Only some documents searchable
- Ingestion interrupted
- Inconsistent result counts

### Diagnosis
```bash
# Check ingestion logs
grep -i "error\|failed\|exception" logs/ingestion.log

# Count indexed documents per domain
python -c "
import json
with open('vector_db/metadata.json') as f:
    meta = json.load(f)

domains = {}
for entry in meta:
    domain = entry.get('domain', 'unknown')
    domains[domain] = domains.get(domain, 0) + 1

for domain, count in sorted(domains.items()):
    print(f'{domain}: {count} chunks')
"
```

### Resolution

**Resume ingestion:**
```bash
# Continue from where it stopped (if supported)
python ingest_vehicle_manual.py --continue
```

**Re-ingest missing domain:**
```bash
python ingest_vehicle_manual.py --domain vehicle --append
```

---

## Recovery Procedures

### Full Index Rebuild

```bash
#!/bin/bash
# full_rebuild.sh

set -e

echo "=== Full Index Rebuild ==="

# Backup existing (if any)
if [ -f "vector_db/faiss_index.bin" ]; then
    timestamp=$(date +%Y%m%d_%H%M%S)
    mkdir -p vector_db/backups
    cp vector_db/faiss_index.bin vector_db/backups/faiss_index.bin.$timestamp
    cp vector_db/bm25_index.pkl vector_db/backups/bm25_index.pkl.$timestamp
    cp vector_db/metadata.json vector_db/backups/metadata.json.$timestamp
    echo "Backed up existing indices"
fi

# Clear existing
rm -f vector_db/faiss_index.bin vector_db/bm25_index.pkl vector_db/metadata.json

# Rebuild
echo "Rebuilding indices..."
python ingest_vehicle_manual.py --rebuild --all-domains

# Verify
python -c "
import faiss
import json
index = faiss.read_index('vector_db/faiss_index.bin')
with open('vector_db/metadata.json') as f:
    meta = json.load(f)
print(f'Rebuild complete: {index.ntotal} vectors, {len(meta)} metadata entries')
assert index.ntotal == len(meta), 'Count mismatch!'
"

echo "=== Rebuild Complete ==="
```

### Backup Script

```bash
#!/bin/bash
# backup_indices.sh

BACKUP_DIR="vector_db/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

for file in faiss_index.bin bm25_index.pkl metadata.json; do
    if [ -f "vector_db/$file" ]; then
        cp "vector_db/$file" "$BACKUP_DIR/${file}.$TIMESTAMP"
        echo "Backed up: $file"
    fi
done

# Keep only last 10 backups per file
for pattern in faiss_index.bin bm25_index.pkl metadata.json; do
    ls -t $BACKUP_DIR/${pattern}.* 2>/dev/null | tail -n +11 | xargs -r rm
done

echo "Backup complete: $TIMESTAMP"
```

---

## Index Health Check Script

Save as `check_index_health.py`:

```python
#!/usr/bin/env python3
"""Verify index integrity."""

import sys
import json
import pickle
import hashlib
from pathlib import Path

def check_file(path, description):
    """Check if file exists and has content."""
    if not path.exists():
        print(f"✗ {description}: MISSING")
        return False
    size = path.stat().st_size
    if size == 0:
        print(f"✗ {description}: EMPTY")
        return False
    print(f"✓ {description}: {size:,} bytes")
    return True

def main():
    vector_db = Path("vector_db")
    issues = []
    
    print("=== Index Health Check ===\n")
    
    # Check files exist
    files_ok = all([
        check_file(vector_db / "faiss_index.bin", "FAISS index"),
        check_file(vector_db / "bm25_index.pkl", "BM25 index"),
        check_file(vector_db / "metadata.json", "Metadata"),
    ])
    
    if not files_ok:
        print("\n⚠ Missing files - run rebuild")
        sys.exit(1)
    
    print("\n--- Loading indices ---")
    
    # Load and verify FAISS
    try:
        import faiss
        index = faiss.read_index(str(vector_db / "faiss_index.bin"))
        faiss_count = index.ntotal
        print(f"✓ FAISS: {faiss_count:,} vectors")
    except Exception as e:
        print(f"✗ FAISS: {e}")
        issues.append("FAISS corrupted")
        faiss_count = -1
    
    # Load and verify BM25
    try:
        with open(vector_db / "bm25_index.pkl", "rb") as f:
            bm25 = pickle.load(f)
        bm25_count = len(bm25.doc_len)
        print(f"✓ BM25: {bm25_count:,} documents")
    except Exception as e:
        print(f"✗ BM25: {e}")
        issues.append("BM25 corrupted")
        bm25_count = -1
    
    # Load and verify metadata
    try:
        with open(vector_db / "metadata.json") as f:
            meta = json.load(f)
        meta_count = len(meta)
        print(f"✓ Metadata: {meta_count:,} entries")
    except Exception as e:
        print(f"✗ Metadata: {e}")
        issues.append("Metadata corrupted")
        meta_count = -1
    
    # Check consistency
    print("\n--- Consistency Check ---")
    
    if faiss_count >= 0 and meta_count >= 0:
        if faiss_count == meta_count:
            print(f"✓ FAISS-Metadata: aligned ({faiss_count})")
        else:
            print(f"✗ FAISS-Metadata: MISMATCH ({faiss_count} vs {meta_count})")
            issues.append("FAISS-Metadata mismatch")
    
    # Summary
    print("\n--- Summary ---")
    if issues:
        print(f"⚠ Issues found: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("✓ All indices healthy")
        sys.exit(0)

if __name__ == "__main__":
    main()
```

---

## Escalation

If recovery fails:

1. Preserve corrupted files for analysis:
   ```bash
   mkdir -p vector_db/corrupted
   cp vector_db/*.bin vector_db/*.pkl vector_db/*.json vector_db/corrupted/
   ```

2. Collect diagnostic info:
   ```bash
   python check_index_health.py > index_health.txt 2>&1
   ls -la vector_db/ > index_files.txt
   ```

3. Open issue with:
   - Error messages
   - Health check output
   - Recent operations (ingestion, updates)
   - Disk space status

---

## Related Runbooks

- [Server Startup Issues](server-startup-issues.md)
- [Backup & Recovery](../operations/BACKUP_RECOVERY.md)
