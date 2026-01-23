"""
Unit tests for corpus manifest and file-hash tracking.

Tests cover:
- SHA-256 hash computation
- Manifest creation, save, and load
- Change detection (new, modified, deleted, unchanged files)
- Manifest integrity validation
- Chunk ID management
"""

import hashlib

from core.indexing.corpus_manifest import (
    CorpusManifest,
    FileMetadata,
    FileChange,
    ChangeType,
    compute_file_hash,
    detect_changes,
    get_next_chunk_id,
)


class TestFileHashing:
    """Test SHA-256 hash computation."""
    
    def test_compute_file_hash_basic(self, tmp_path):
        """Test basic file hash computation."""
        # Create test file
        test_file = tmp_path / "test.txt"
        content = b"Hello, Phase 3!"
        test_file.write_bytes(content)
        
        # Compute hash
        file_hash = compute_file_hash(test_file)
        
        # Verify against expected hash
        expected_hash = hashlib.sha256(content).hexdigest()
        assert file_hash == expected_hash
    
    def test_compute_file_hash_large_file(self, tmp_path):
        """Test hash computation for large file (> chunk size)."""
        test_file = tmp_path / "large.txt"
        # Create 100KB file
        content = b"x" * (100 * 1024)
        test_file.write_bytes(content)
        
        file_hash = compute_file_hash(test_file)
        expected_hash = hashlib.sha256(content).hexdigest()
        
        assert file_hash == expected_hash
    
    def test_compute_file_hash_deterministic(self, tmp_path):
        """Test that same content produces same hash."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Deterministic content", encoding='utf-8')
        
        hash1 = compute_file_hash(test_file)
        hash2 = compute_file_hash(test_file)
        
        assert hash1 == hash2
    
    def test_compute_file_hash_different_content(self, tmp_path):
        """Test that different content produces different hashes."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        
        file1.write_text("Content A", encoding='utf-8')
        file2.write_text("Content B", encoding='utf-8')
        
        hash1 = compute_file_hash(file1)
        hash2 = compute_file_hash(file2)
        
        assert hash1 != hash2


class TestFileMetadata:
    """Test FileMetadata dataclass."""
    
    def test_metadata_creation(self):
        """Test creating metadata instance."""
        metadata = FileMetadata(
            sha256="abc123",
            chunk_count=10,
            domain="vehicle_civilian",
            last_modified="2026-01-22T10:00:00Z",
            ingested_at="2026-01-22T10:30:00Z",
            chunk_ids=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
            file_size=1024
        )
        
        assert metadata.sha256 == "abc123"
        assert metadata.chunk_count == 10
        assert metadata.domain == "vehicle_civilian"
        assert len(metadata.chunk_ids) == 10
    
    def test_metadata_to_dict(self):
        """Test metadata serialization to dict."""
        metadata = FileMetadata(
            sha256="abc123",
            chunk_count=5,
            domain="forklift",
            last_modified="2026-01-22T10:00:00Z",
            ingested_at="2026-01-22T10:30:00Z",
            chunk_ids=[0, 1, 2, 3, 4]
        )
        
        data = metadata.to_dict()
        
        assert data["sha256"] == "abc123"
        assert data["chunk_count"] == 5
        assert data["domain"] == "forklift"
        assert data["chunk_ids"] == [0, 1, 2, 3, 4]
    
    def test_metadata_from_dict(self):
        """Test metadata deserialization from dict."""
        data = {
            "sha256": "def456",
            "chunk_count": 3,
            "domain": "hvac",
            "last_modified": "2026-01-22T10:00:00Z",
            "ingested_at": "2026-01-22T10:30:00Z",
            "chunk_ids": [10, 11, 12],
            "file_size": 2048
        }
        
        metadata = FileMetadata.from_dict(data)
        
        assert metadata.sha256 == "def456"
        assert metadata.chunk_count == 3
        assert metadata.domain == "hvac"
        assert metadata.chunk_ids == [10, 11, 12]


class TestCorpusManifest:
    """Test CorpusManifest class."""
    
    def test_manifest_creation_empty(self):
        """Test creating empty manifest."""
        manifest = CorpusManifest()
        
        assert manifest.version == "3.0"
        assert manifest.total_chunks == 0
        assert len(manifest.files) == 0
    
    def test_manifest_add_file(self):
        """Test adding file to manifest."""
        manifest = CorpusManifest()
        
        manifest.add_file(
            file_path="data/test.pdf",
            sha256="abc123",
            chunk_count=10,
            chunk_ids=list(range(10)),
            domain="vehicle_civilian"
        )
        
        assert len(manifest.files) == 1
        assert manifest.total_chunks == 10
        assert "data/test.pdf" in manifest.files
        assert manifest.files["data/test.pdf"].sha256 == "abc123"
    
    def test_manifest_add_multiple_files(self):
        """Test adding multiple files to manifest."""
        manifest = CorpusManifest()
        
        manifest.add_file("file1.pdf", "hash1", 10, list(range(10)), "vehicle")
        manifest.add_file("file2.pdf", "hash2", 5, list(range(10, 15)), "forklift")
        
        assert len(manifest.files) == 2
        assert manifest.total_chunks == 15
    
    def test_manifest_remove_file(self):
        """Test removing file from manifest."""
        manifest = CorpusManifest()
        manifest.add_file("test.pdf", "hash1", 10, list(range(10)), "vehicle")
        
        metadata = manifest.remove_file("test.pdf")
        
        assert metadata is not None
        assert metadata.sha256 == "hash1"
        assert len(manifest.files) == 0
        assert manifest.total_chunks == 0
    
    def test_manifest_remove_nonexistent_file(self):
        """Test removing file that doesn't exist."""
        manifest = CorpusManifest()
        
        metadata = manifest.remove_file("nonexistent.pdf")
        
        assert metadata is None
    
    def test_manifest_save_load(self, tmp_path):
        """Test saving and loading manifest."""
        manifest_path = tmp_path / "manifest.json"
        
        # Create manifest
        manifest = CorpusManifest()
        manifest.add_file("test.pdf", "abc123", 10, list(range(10)), "vehicle")
        
        # Save
        manifest.save(manifest_path)
        assert manifest_path.exists()
        
        # Load
        loaded = CorpusManifest.load(manifest_path)
        
        assert loaded.total_chunks == 10
        assert len(loaded.files) == 1
        assert loaded.files["test.pdf"].sha256 == "abc123"
    
    def test_manifest_load_nonexistent(self, tmp_path):
        """Test loading manifest that doesn't exist."""
        manifest_path = tmp_path / "nonexistent.json"
        
        manifest = CorpusManifest.load(manifest_path)
        
        assert len(manifest.files) == 0
        assert manifest.total_chunks == 0
    
    def test_manifest_to_dict(self):
        """Test manifest serialization."""
        manifest = CorpusManifest()
        manifest.add_file("test.pdf", "hash1", 5, list(range(5)), "vehicle")
        
        data = manifest.to_dict()
        
        assert data["version"] == "3.0"
        assert data["total_chunks"] == 5
        assert "test.pdf" in data["files"]
    
    def test_manifest_from_dict(self):
        """Test manifest deserialization."""
        data = {
            "version": "3.0",
            "last_updated": "2026-01-22T10:00:00Z",
            "total_chunks": 5,
            "files": {
                "test.pdf": {
                    "sha256": "hash1",
                    "chunk_count": 5,
                    "domain": "vehicle",
                    "last_modified": "2026-01-22T09:00:00Z",
                    "ingested_at": "2026-01-22T10:00:00Z",
                    "chunk_ids": [0, 1, 2, 3, 4],
                    "file_size": 1024
                }
            }
        }
        
        manifest = CorpusManifest.from_dict(data)
        
        assert manifest.total_chunks == 5
        assert len(manifest.files) == 1
        assert manifest.files["test.pdf"].sha256 == "hash1"


class TestChangeDetection:
    """Test change detection logic."""
    
    def test_detect_new_files(self, tmp_path):
        """Test detecting new files."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        # Create test file
        test_file = corpus_dir / "new.txt"
        test_file.write_text("New content", encoding='utf-8')
        
        # Empty manifest
        manifest = CorpusManifest()
        
        # Detect changes
        changes = detect_changes(corpus_dir, manifest, file_extensions={'.txt'})
        
        assert len(changes) == 1
        assert changes[0].change_type == ChangeType.NEW
        assert changes[0].file_path == "new.txt"
    
    def test_detect_modified_files(self, tmp_path):
        """Test detecting modified files."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        # Create test file
        test_file = corpus_dir / "modified.txt"
        test_file.write_text("Original content", encoding='utf-8')
        
        # Create manifest with old hash
        manifest = CorpusManifest()
        manifest.add_file("modified.txt", "old_hash", 1, [0], "vehicle")
        
        # Modify file
        test_file.write_text("Modified content", encoding='utf-8')
        
        # Detect changes
        changes = detect_changes(corpus_dir, manifest, file_extensions={'.txt'})
        
        modified_changes = [c for c in changes if c.change_type == ChangeType.MODIFIED]
        assert len(modified_changes) == 1
        assert modified_changes[0].file_path == "modified.txt"
    
    def test_detect_deleted_files(self, tmp_path):
        """Test detecting deleted files."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        # Manifest references file that doesn't exist
        manifest = CorpusManifest()
        manifest.add_file("deleted.txt", "hash1", 1, [0], "vehicle")
        
        # Detect changes
        changes = detect_changes(corpus_dir, manifest, file_extensions={'.txt'})
        
        deleted_changes = [c for c in changes if c.change_type == ChangeType.DELETED]
        assert len(deleted_changes) == 1
        assert deleted_changes[0].file_path == "deleted.txt"
    
    def test_detect_unchanged_files(self, tmp_path):
        """Test detecting unchanged files."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        # Create test file
        test_file = corpus_dir / "unchanged.txt"
        content = "Unchanged content"
        test_file.write_text(content, encoding='utf-8')
        
        # Manifest with correct hash
        file_hash = compute_file_hash(test_file)
        manifest = CorpusManifest()
        manifest.add_file("unchanged.txt", file_hash, 1, [0], "vehicle")
        
        # Detect changes
        changes = detect_changes(corpus_dir, manifest, file_extensions={'.txt'})
        
        unchanged_changes = [c for c in changes if c.change_type == ChangeType.UNCHANGED]
        assert len(unchanged_changes) == 1
        assert unchanged_changes[0].file_path == "unchanged.txt"
    
    def test_detect_multiple_change_types(self, tmp_path):
        """Test detecting mix of new, modified, deleted, unchanged."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        # Create manifest with some files
        manifest = CorpusManifest()
        
        # File 1: Unchanged
        file1 = corpus_dir / "unchanged.txt"
        file1.write_text("Content 1", encoding='utf-8')
        hash1 = compute_file_hash(file1)
        manifest.add_file("unchanged.txt", hash1, 1, [0], "vehicle")
        
        # File 2: Will be modified
        file2 = corpus_dir / "modified.txt"
        file2.write_text("Original", encoding='utf-8')
        manifest.add_file("modified.txt", "old_hash", 1, [1], "vehicle")
        
        # File 3: Will be deleted (exists in manifest only)
        manifest.add_file("deleted.txt", "hash3", 1, [2], "vehicle")
        
        # File 4: New file (create after manifest)
        file4 = corpus_dir / "new.txt"
        file4.write_text("New content", encoding='utf-8')
        
        # Detect changes
        changes = detect_changes(corpus_dir, manifest, file_extensions={'.txt'})
        
        change_types = {c.change_type for c in changes}
        assert ChangeType.NEW in change_types
        assert ChangeType.MODIFIED in change_types
        assert ChangeType.DELETED in change_types
        assert ChangeType.UNCHANGED in change_types


class TestManifestValidation:
    """Test manifest integrity validation."""
    
    def test_validate_integrity_valid(self, tmp_path):
        """Test validation of valid manifest."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        # Create test file
        test_file = corpus_dir / "test.txt"
        test_file.write_text("Content", encoding='utf-8')
        
        # Create valid manifest
        manifest = CorpusManifest()
        manifest.add_file("test.txt", "hash1", 3, [0, 1, 2], "vehicle")
        
        errors = manifest.validate_integrity(corpus_dir)
        
        assert len(errors) == 0
    
    def test_validate_integrity_missing_file(self, tmp_path):
        """Test validation detects missing files."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        # Manifest references non-existent file
        manifest = CorpusManifest()
        manifest.add_file("missing.txt", "hash1", 1, [0], "vehicle")
        
        errors = manifest.validate_integrity(corpus_dir)
        
        assert len(errors) > 0
        assert any("missing file" in e.lower() for e in errors)
    
    def test_validate_integrity_duplicate_chunk_ids(self, tmp_path):
        """Test validation detects duplicate chunk IDs."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        # Create files
        file1 = corpus_dir / "file1.txt"
        file2 = corpus_dir / "file2.txt"
        file1.write_text("Content 1", encoding='utf-8')
        file2.write_text("Content 2", encoding='utf-8')
        
        # Create manifest with duplicate chunk IDs
        manifest = CorpusManifest()
        manifest.files["file1.txt"] = FileMetadata(
            sha256="hash1", chunk_count=3, domain="vehicle",
            last_modified="2026-01-22T10:00:00Z",
            ingested_at="2026-01-22T10:30:00Z",
            chunk_ids=[0, 1, 2]  # Duplicate IDs
        )
        manifest.files["file2.txt"] = FileMetadata(
            sha256="hash2", chunk_count=3, domain="vehicle",
            last_modified="2026-01-22T10:00:00Z",
            ingested_at="2026-01-22T10:30:00Z",
            chunk_ids=[1, 2, 3]  # Overlaps with file1
        )
        manifest.total_chunks = 6
        
        errors = manifest.validate_integrity(corpus_dir)
        
        assert len(errors) > 0
        assert any("duplicate" in e.lower() for e in errors)
    
    def test_validate_integrity_total_chunks_mismatch(self, tmp_path):
        """Test validation detects total_chunks mismatch."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        file1 = corpus_dir / "file1.txt"
        file1.write_text("Content", encoding='utf-8')
        
        # Create manifest with wrong total_chunks
        manifest = CorpusManifest()
        manifest.files["file1.txt"] = FileMetadata(
            sha256="hash1", chunk_count=5, domain="vehicle",
            last_modified="2026-01-22T10:00:00Z",
            ingested_at="2026-01-22T10:30:00Z",
            chunk_ids=[0, 1, 2, 3, 4]
        )
        manifest.total_chunks = 100  # Wrong!
        
        errors = manifest.validate_integrity(corpus_dir)
        
        assert len(errors) > 0
        assert any("total_chunks" in e for e in errors)


class TestChunkIDManagement:
    """Test chunk ID allocation."""
    
    def test_get_next_chunk_id_empty_manifest(self):
        """Test getting first chunk ID from empty manifest."""
        manifest = CorpusManifest()
        
        next_id = get_next_chunk_id(manifest)
        
        assert next_id == 0
    
    def test_get_next_chunk_id_with_files(self):
        """Test getting next chunk ID with existing files."""
        manifest = CorpusManifest()
        manifest.add_file("file1.pdf", "hash1", 5, [0, 1, 2, 3, 4], "vehicle")
        manifest.add_file("file2.pdf", "hash2", 3, [5, 6, 7], "forklift")
        
        next_id = get_next_chunk_id(manifest)
        
        assert next_id == 8
    
    def test_get_next_chunk_id_non_sequential(self):
        """Test chunk ID allocation with gaps (after deletion)."""
        manifest = CorpusManifest()
        # Simulate scenario where file with chunks [5,6,7] was deleted
        manifest.add_file("file1.pdf", "hash1", 5, [0, 1, 2, 3, 4], "vehicle")
        manifest.add_file("file3.pdf", "hash3", 3, [8, 9, 10], "forklift")
        
        next_id = get_next_chunk_id(manifest)
        
        # Should be 11, not reusing gap at [5,6,7]
        assert next_id == 11


class TestFileChangeDataclass:
    """Test FileChange dataclass."""
    
    def test_file_change_string_representation(self):
        """Test string representation of file changes."""
        change = FileChange(
            file_path="test.pdf",
            change_type=ChangeType.NEW
        )
        
        assert "new" in str(change).lower()
        assert "test.pdf" in str(change)
    
    def test_file_change_with_metadata(self):
        """Test file change with old metadata."""
        old_meta = FileMetadata(
            sha256="old_hash",
            chunk_count=5,
            domain="vehicle",
            last_modified="2026-01-20T10:00:00Z",
            ingested_at="2026-01-20T10:30:00Z",
            chunk_ids=[0, 1, 2, 3, 4]
        )
        
        change = FileChange(
            file_path="modified.pdf",
            change_type=ChangeType.MODIFIED,
            old_metadata=old_meta,
            new_hash="new_hash"
        )
        
        assert change.old_metadata is not None
        assert change.old_metadata.sha256 == "old_hash"
        assert change.new_hash == "new_hash"
