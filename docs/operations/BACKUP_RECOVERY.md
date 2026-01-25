# Backup & Recovery Procedures

This document describes backup and recovery procedures for the Nova NIC system.

---

## Components to Backup

| Component | Location | Frequency | Priority |
|-----------|----------|-----------|----------|
| FAISS Index | `vector_db/faiss_index.bin` | Daily + before ingestion | Critical |
| BM25 Index | `vector_db/bm25_index.pkl` | Daily + before ingestion | Critical |
| Metadata | `vector_db/metadata.json` | Daily + before ingestion | Critical |
| Configuration | `.env`, `config/` | On change | High |
| Session Data | `cache/sessions/` | Optional | Low |
| Source Documents | `data/` | Weekly | Medium |
| Logs | `logs/` | Daily rotation | Medium |

---

## Backup Procedures

### Automated Daily Backup

Create `/etc/cron.daily/nova-backup`:

```bash
#!/bin/bash
# Nova NIC Daily Backup Script

set -e

# Configuration
BACKUP_DIR="/var/backups/nova-nic"
NOVA_DIR="/opt/nova-nic"
RETENTION_DAYS=30
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR/$DATE"

# Backup indices
echo "Backing up indices..."
cp "$NOVA_DIR/vector_db/faiss_index.bin" "$BACKUP_DIR/$DATE/"
cp "$NOVA_DIR/vector_db/bm25_index.pkl" "$BACKUP_DIR/$DATE/"
cp "$NOVA_DIR/vector_db/metadata.json" "$BACKUP_DIR/$DATE/"

# Backup configuration
echo "Backing up configuration..."
cp "$NOVA_DIR/.env" "$BACKUP_DIR/$DATE/" 2>/dev/null || true
cp -r "$NOVA_DIR/config/" "$BACKUP_DIR/$DATE/" 2>/dev/null || true

# Create tarball
echo "Creating archive..."
tar -czf "$BACKUP_DIR/nova-backup-$DATE.tar.gz" -C "$BACKUP_DIR" "$DATE"
rm -rf "$BACKUP_DIR/$DATE"

# Calculate checksum
sha256sum "$BACKUP_DIR/nova-backup-$DATE.tar.gz" > "$BACKUP_DIR/nova-backup-$DATE.tar.gz.sha256"

# Cleanup old backups
echo "Cleaning up old backups..."
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name "*.sha256" -mtime +$RETENTION_DAYS -delete

echo "Backup complete: nova-backup-$DATE.tar.gz"
```

Make executable:
```bash
chmod +x /etc/cron.daily/nova-backup
```

### Pre-Ingestion Backup

Run before any document ingestion:

```bash
#!/bin/bash
# pre_ingest_backup.sh

BACKUP_DIR="vector_db/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

echo "Creating pre-ingestion backup..."

for file in faiss_index.bin bm25_index.pkl metadata.json; do
    if [ -f "vector_db/$file" ]; then
        cp "vector_db/$file" "$BACKUP_DIR/${file}.pre_ingest_$TIMESTAMP"
        echo "  Backed up: $file"
    fi
done

echo "Pre-ingestion backup complete: $TIMESTAMP"
```

### Full System Backup

For complete disaster recovery:

```bash
#!/bin/bash
# full_backup.sh

set -e

BACKUP_DIR="/var/backups/nova-nic-full"
DATE=$(date +%Y%m%d)
NOVA_DIR="/opt/nova-nic"

echo "=== Nova NIC Full System Backup ==="

mkdir -p "$BACKUP_DIR"

# Stop service for consistent backup
echo "Stopping service..."
sudo systemctl stop nova-nic

# Create full backup
echo "Creating full backup..."
tar -czf "$BACKUP_DIR/nova-full-$DATE.tar.gz" \
    --exclude="$NOVA_DIR/.venv" \
    --exclude="$NOVA_DIR/__pycache__" \
    --exclude="$NOVA_DIR/logs/*.log" \
    -C "$(dirname $NOVA_DIR)" \
    "$(basename $NOVA_DIR)"

# Restart service
echo "Restarting service..."
sudo systemctl start nova-nic

# Checksum
sha256sum "$BACKUP_DIR/nova-full-$DATE.tar.gz" > "$BACKUP_DIR/nova-full-$DATE.tar.gz.sha256"

echo "Full backup complete: nova-full-$DATE.tar.gz"
echo "Size: $(du -h $BACKUP_DIR/nova-full-$DATE.tar.gz | cut -f1)"
```

---

## Remote Backup

### AWS S3

```bash
#!/bin/bash
# s3_backup.sh

BUCKET="your-backup-bucket"
PREFIX="nova-nic/backups"
LOCAL_BACKUP="/var/backups/nova-nic"

# Sync to S3
aws s3 sync "$LOCAL_BACKUP" "s3://$BUCKET/$PREFIX/" \
    --storage-class STANDARD_IA \
    --exclude "*.tmp"

# List recent backups
echo "Recent S3 backups:"
aws s3 ls "s3://$BUCKET/$PREFIX/" | tail -10
```

### Rsync to Remote Server

```bash
#!/bin/bash
# remote_backup.sh

REMOTE_HOST="backup-server.example.com"
REMOTE_PATH="/backups/nova-nic"
LOCAL_BACKUP="/var/backups/nova-nic"

# Sync with compression
rsync -avz --progress \
    "$LOCAL_BACKUP/" \
    "$REMOTE_HOST:$REMOTE_PATH/"
```

---

## Recovery Procedures

### Quick Index Recovery

Restore indices from local backup:

```bash
#!/bin/bash
# quick_restore.sh

BACKUP_DIR="vector_db/backups"

# List available backups
echo "Available backups:"
ls -lt "$BACKUP_DIR"/*.pre_ingest_* 2>/dev/null | head -10

echo ""
read -p "Enter backup timestamp (e.g., 20260125_143000): " TIMESTAMP

# Stop service
echo "Stopping service..."
sudo systemctl stop nova-nic

# Restore files
for file in faiss_index.bin bm25_index.pkl metadata.json; do
    backup_file="$BACKUP_DIR/${file}.pre_ingest_$TIMESTAMP"
    if [ -f "$backup_file" ]; then
        cp "$backup_file" "vector_db/$file"
        echo "Restored: $file"
    else
        echo "Warning: $backup_file not found"
    fi
done

# Restart service
echo "Starting service..."
sudo systemctl start nova-nic

echo "Recovery complete"
```

### Full System Recovery

Restore from full backup:

```bash
#!/bin/bash
# full_restore.sh

set -e

BACKUP_FILE="$1"
NOVA_DIR="/opt/nova-nic"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

echo "=== Nova NIC Full System Recovery ==="

# Verify checksum
if [ -f "${BACKUP_FILE}.sha256" ]; then
    echo "Verifying checksum..."
    sha256sum -c "${BACKUP_FILE}.sha256"
fi

# Stop service
echo "Stopping service..."
sudo systemctl stop nova-nic || true

# Backup current (in case of issues)
if [ -d "$NOVA_DIR" ]; then
    echo "Backing up current installation..."
    mv "$NOVA_DIR" "${NOVA_DIR}.old.$(date +%s)"
fi

# Extract backup
echo "Extracting backup..."
mkdir -p "$(dirname $NOVA_DIR)"
tar -xzf "$BACKUP_FILE" -C "$(dirname $NOVA_DIR)"

# Set permissions
chown -R nova:nova "$NOVA_DIR"

# Recreate virtual environment
echo "Setting up Python environment..."
cd "$NOVA_DIR"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Start service
echo "Starting service..."
sudo systemctl start nova-nic

# Verify
echo "Verifying..."
sleep 5
curl -s http://localhost:5000/health | jq '.status'

echo "Recovery complete"
```

### Recover from S3

```bash
#!/bin/bash
# s3_restore.sh

BUCKET="your-backup-bucket"
PREFIX="nova-nic/backups"
LOCAL_DIR="/var/backups/nova-nic"

# List available backups
echo "Available S3 backups:"
aws s3 ls "s3://$BUCKET/$PREFIX/" | grep ".tar.gz" | tail -10

echo ""
read -p "Enter backup filename: " FILENAME

# Download
aws s3 cp "s3://$BUCKET/$PREFIX/$FILENAME" "$LOCAL_DIR/"
aws s3 cp "s3://$BUCKET/$PREFIX/$FILENAME.sha256" "$LOCAL_DIR/" 2>/dev/null || true

echo "Downloaded to: $LOCAL_DIR/$FILENAME"
echo "Run: ./full_restore.sh $LOCAL_DIR/$FILENAME"
```

---

## Verification Procedures

### Post-Backup Verification

```bash
#!/bin/bash
# verify_backup.sh

BACKUP_FILE="$1"

if [ -z "$BACKUP_FILE" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

echo "=== Backup Verification ==="

# Check file exists and has size
if [ ! -f "$BACKUP_FILE" ]; then
    echo "ERROR: Backup file not found"
    exit 1
fi

SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
echo "File size: $SIZE"

# Verify checksum
if [ -f "${BACKUP_FILE}.sha256" ]; then
    echo "Verifying checksum..."
    if sha256sum -c "${BACKUP_FILE}.sha256"; then
        echo "✓ Checksum valid"
    else
        echo "✗ Checksum FAILED"
        exit 1
    fi
fi

# Test archive integrity
echo "Testing archive integrity..."
if tar -tzf "$BACKUP_FILE" > /dev/null 2>&1; then
    echo "✓ Archive valid"
else
    echo "✗ Archive corrupted"
    exit 1
fi

# List contents
echo ""
echo "Archive contents:"
tar -tzf "$BACKUP_FILE" | head -20

echo ""
echo "✓ Backup verification passed"
```

### Post-Recovery Verification

```bash
#!/bin/bash
# verify_recovery.sh

echo "=== Post-Recovery Verification ==="

# Check service status
echo "1. Service status:"
sudo systemctl status nova-nic --no-pager | head -5

# Check health endpoint
echo ""
echo "2. Health check:"
curl -s http://localhost:5000/health | jq '.'

# Check index counts
echo ""
echo "3. Index verification:"
python3 -c "
import faiss
import json

index = faiss.read_index('vector_db/faiss_index.bin')
with open('vector_db/metadata.json') as f:
    meta = json.load(f)

print(f'FAISS vectors: {index.ntotal}')
print(f'Metadata entries: {len(meta)}')
print(f'Match: {index.ntotal == len(meta)}')
"

# Test query
echo ""
echo "4. Test query:"
curl -s -X POST http://localhost:5000/api/ask \
    -H "Content-Type: application/json" \
    -d '{"query": "How do I check brake pads?"}' | jq '.answer[:100]'

echo ""
echo "=== Verification Complete ==="
```

---

## Disaster Recovery Scenarios

### Scenario 1: Corrupted Index

**Symptoms:** Retrieval errors, empty results

**Recovery:**
1. Stop service
2. Restore from latest backup: `./quick_restore.sh`
3. Verify: `./verify_recovery.sh`

**RTO:** 5 minutes  
**RPO:** Last backup (typically same day)

### Scenario 2: Complete Server Loss

**Symptoms:** Server unreachable, hardware failure

**Recovery:**
1. Provision new server
2. Install dependencies (Python, Ollama)
3. Download backup from S3: `./s3_restore.sh`
4. Run full restore: `./full_restore.sh`
5. Update DNS/load balancer

**RTO:** 30-60 minutes  
**RPO:** Last remote backup

### Scenario 3: Accidental Data Deletion

**Symptoms:** Missing documents, reduced search results

**Recovery:**
1. Identify what was deleted
2. Restore specific files from backup
3. Or: full index rebuild from source documents

**RTO:** 15-30 minutes  
**RPO:** Last backup or source documents

### Scenario 4: Database Corruption After Bad Ingestion

**Symptoms:** Errors after ingesting new documents

**Recovery:**
1. Restore pre-ingestion backup: 
   ```bash
   cp vector_db/backups/*.pre_ingest_TIMESTAMP vector_db/
   ```
2. Investigate ingestion issue
3. Fix source documents
4. Re-ingest

**RTO:** 5 minutes  
**RPO:** Pre-ingestion state

---

## Backup Retention Policy

| Backup Type | Retention | Storage |
|-------------|-----------|---------|
| Hourly snapshots | 24 hours | Local |
| Daily backups | 30 days | Local + Remote |
| Weekly backups | 12 weeks | Remote |
| Monthly backups | 12 months | Remote (cold) |
| Pre-ingestion | 7 days | Local |

---

## Monitoring Backups

### Prometheus Metrics

```python
# In backup script, export metrics
from prometheus_client import Gauge, push_to_gateway

backup_success = Gauge('nova_backup_success', 'Last backup success (1/0)')
backup_size = Gauge('nova_backup_size_bytes', 'Last backup size')
backup_age = Gauge('nova_backup_age_seconds', 'Age of last backup')
```

### Alert on Missing Backups

```yaml
# prometheus/alerts/backup.yml
groups:
  - name: backup
    rules:
      - alert: BackupMissing
        expr: time() - nova_backup_timestamp > 86400 * 2
        for: 1h
        labels:
          severity: warning
        annotations:
          summary: "No backup in 48 hours"
          
      - alert: BackupFailed
        expr: nova_backup_success == 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Last backup failed"
```

---

## Recovery Testing

### Monthly Recovery Drill

1. **Select random backup** (not latest)
2. **Restore to test environment**
3. **Run verification suite**
4. **Document results**

```bash
#!/bin/bash
# recovery_drill.sh

echo "=== Monthly Recovery Drill ==="
echo "Date: $(date)"

# Select random backup
BACKUP=$(ls -t /var/backups/nova-nic/*.tar.gz | shuf | head -1)
echo "Testing backup: $BACKUP"

# Restore to test environment
TEST_DIR="/tmp/nova-recovery-test"
mkdir -p "$TEST_DIR"
tar -xzf "$BACKUP" -C "$TEST_DIR"

# Run tests
cd "$TEST_DIR/nova-nic"
python3 -m pytest tests/test_retrieval.py -v

# Report
echo ""
echo "Recovery drill complete"
echo "Backup tested: $BACKUP"
echo "Result: PASS/FAIL"
```

---

## Contact Information

| Role | Contact | When to Contact |
|------|---------|-----------------|
| On-call Engineer | PagerDuty | Any backup failure |
| Data Team | data@example.com | Large-scale recovery |
| Cloud Team | cloud@example.com | S3/remote storage issues |

---

## Related Documentation

- [Index Corruption Runbook](../runbooks/index-corruption.md)
- [Server Startup Issues](../runbooks/server-startup-issues.md)
- [Monitoring Guide](MONITORING.md)
