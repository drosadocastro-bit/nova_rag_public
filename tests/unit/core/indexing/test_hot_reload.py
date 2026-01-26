"""
Unit tests for hot-reload API endpoint.

Tests cover:
- Dry-run mode
- Progress streaming
- File detection and processing
- Error handling
- Atomic updates
"""

import json
import pytest
from unittest.mock import Mock, patch
import numpy as np

from core.indexing.hot_reload import (
    IncrementalReloader,
    ReloadProgress,
    ReloadResult,
    create_reload_endpoint,
)
from core.indexing import (
    CorpusManifest,
    IncrementalFAISSIndex,
)
from core.indexing.incremental_bm25 import IncrementalBM25


class TestReloadProgress:
    """Test ReloadProgress dataclass."""
    
    def test_progress_creation(self):
        """Test creating progress update."""
        progress = ReloadProgress(
            stage="test",
            current=5,
            total=10,
            message="Testing"
        )
        
        assert progress.stage == "test"
        assert progress.current == 5
        assert progress.total == 10
        assert progress.message == "Testing"
        assert progress.timestamp is not None
    
    def test_progress_to_json(self):
        """Test JSON serialization."""
        progress = ReloadProgress(
            stage="test",
            current=1,
            total=5,
            message="Test message"
        )
        
        json_str = progress.to_json()
        data = json.loads(json_str.strip())
        
        assert data["stage"] == "test"
        assert data["current"] == 1
        assert data["total"] == 5
        assert data["message"] == "Test message"


class TestReloadResult:
    """Test ReloadResult dataclass."""
    
    def test_result_creation(self):
        """Test creating reload result."""
        result = ReloadResult(
            success=True,
            dry_run=False,
            files_added=3,
            files_modified=1,
            files_deleted=0,
            chunks_added=150,
            duration_seconds=2.5,
            errors=[],
            manifest_path="/path/to/manifest.json"
        )
        
        assert result.success is True
        assert result.files_added == 3
        assert result.chunks_added == 150
        assert len(result.errors) == 0
    
    def test_result_with_errors(self):
        """Test result with errors."""
        result = ReloadResult(
            success=False,
            dry_run=False,
            files_added=0,
            files_modified=0,
            files_deleted=0,
            chunks_added=0,
            duration_seconds=1.0,
            errors=["Error 1", "Error 2"],
            manifest_path="/path/to/manifest.json"
        )
        
        assert result.success is False
        assert len(result.errors) == 2


class TestIncrementalReloader:
    """Test IncrementalReloader class."""
    
    @pytest.fixture
    def mock_components(self, tmp_path):
        """Create mock components for reloader."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        manifest_path = tmp_path / "manifest.json"
        
        # Create mocks
        faiss_index = Mock(spec=IncrementalFAISSIndex)
        faiss_index.add_chunks.return_value = (True, None)
        
        bm25_index = Mock(spec=IncrementalBM25)
        bm25_index.add_documents.return_value = (True, None)
        bm25_index.remove_documents.return_value = (True, None)
        
        embedding_fn = Mock(return_value=np.random.rand(384))
        tokenizer_fn = Mock(return_value=["token1", "token2"])
        domain_tagger_fn = Mock(return_value="test_domain")
        
        return {
            "corpus_dir": corpus_dir,
            "manifest_path": manifest_path,
            "faiss_index": faiss_index,
            "bm25_index": bm25_index,
            "embedding_function": embedding_fn,
            "tokenizer_function": tokenizer_fn,
            "domain_tagger_function": domain_tagger_fn,
        }
    
    def test_reloader_initialization(self, mock_components):
        """Test reloader initialization."""
        reloader = IncrementalReloader(
            corpus_dir=mock_components["corpus_dir"],
            manifest_path=mock_components["manifest_path"],
            faiss_index=mock_components["faiss_index"],
            bm25_index=mock_components["bm25_index"],
            embedding_function=mock_components["embedding_function"],
            tokenizer_function=mock_components["tokenizer_function"],
            domain_tagger_function=mock_components["domain_tagger_function"]
        )
        
        assert reloader.corpus_dir == mock_components["corpus_dir"]
        assert reloader.manifest_path == mock_components["manifest_path"]
    
    def test_reload_dry_run_no_changes(self, mock_components):
        """Test dry-run with no file changes."""
        reloader = IncrementalReloader(**mock_components)
        
        # Create empty manifest
        manifest = CorpusManifest()
        manifest.save(mock_components["manifest_path"])
        
        # Run dry-run
        result = None
        for item in reloader.reload(dry_run=True, stream_progress=False):
            if isinstance(item, ReloadResult):
                result = item
        
        assert result is not None
        assert result.dry_run is True
        assert result.files_added == 0
        assert result.files_modified == 0
        assert result.files_deleted == 0
    
    def test_reload_dry_run_with_new_file(self, mock_components):
        """Test dry-run detecting new file."""
        reloader = IncrementalReloader(**mock_components)
        
        # Create empty manifest
        manifest = CorpusManifest()
        manifest.save(mock_components["manifest_path"])
        
        # Add new file to corpus
        test_file = mock_components["corpus_dir"] / "new.txt"
        test_file.write_text("New content", encoding='utf-8')
        
        # Run dry-run
        result = None
        for item in reloader.reload(dry_run=True, stream_progress=False):
            if isinstance(item, ReloadResult):
                result = item
        
        assert result is not None
        assert result.dry_run is True
        assert result.files_added == 1
        assert result.chunks_added == 0  # Dry-run doesn't add chunks
    
    def test_reload_with_progress_streaming(self, mock_components):
        """Test reload with progress updates."""
        reloader = IncrementalReloader(**mock_components)
        
        # Create empty manifest
        manifest = CorpusManifest()
        manifest.save(mock_components["manifest_path"])
        
        # Collect progress updates
        progress_updates = []
        result = None
        
        for item in reloader.reload(dry_run=True, stream_progress=True):
            if isinstance(item, ReloadProgress):
                progress_updates.append(item)
            elif isinstance(item, ReloadResult):
                result = item
        
        # Should have progress updates
        assert len(progress_updates) > 0
        assert result is not None
        
        # Check progress stages
        stages = [p.stage for p in progress_updates]
        assert "init" in stages
        assert "detect" in stages


class TestCreateReloadEndpoint:
    """Test Flask endpoint creation."""
    
    def test_endpoint_creation(self, tmp_path):
        """Test creating reload endpoint."""
        # Create mock reloader
        reloader = Mock(spec=IncrementalReloader)
        reloader.reload.return_value = iter([
            ReloadResult(
                success=True,
                dry_run=True,
                files_added=0,
                files_modified=0,
                files_deleted=0,
                chunks_added=0,
                duration_seconds=0.1,
                errors=[],
                manifest_path="/test/manifest.json"
            )
        ])
        
        # Create endpoint
        endpoint = create_reload_endpoint(reloader)
        
        assert endpoint is not None
        assert callable(endpoint)
    
    @patch('core.indexing.hot_reload.request')
    def test_endpoint_dry_run(self, mock_request, tmp_path):
        """Test endpoint with dry_run parameter."""
        # Setup mock
        mock_request.args.get.side_effect = lambda key, default: {
            'dry_run': 'true',
            'stream': 'false'
        }.get(key, default)
        
        # Create mock reloader
        reloader = Mock(spec=IncrementalReloader)
        result = ReloadResult(
            success=True,
            dry_run=True,
            files_added=5,
            files_modified=2,
            files_deleted=1,
            chunks_added=0,
            duration_seconds=0.5,
            errors=[],
            manifest_path="/test/manifest.json"
        )
        reloader.reload.return_value = iter([result])
        
        # Create and call endpoint
        endpoint = create_reload_endpoint(reloader)
        endpoint()
        
        # Verify dry_run was passed
        reloader.reload.assert_called_once_with(dry_run=True, stream_progress=False)


class TestReloadErrorHandling:
    """Test error handling in reload operations."""
    
    def test_manifest_load_error(self, tmp_path):
        """Test handling of manifest load error."""
        corpus_dir = tmp_path / "corpus"
        corpus_dir.mkdir()
        
        manifest_path = tmp_path / "nonexistent" / "manifest.json"
        
        faiss_index = Mock(spec=IncrementalFAISSIndex)
        bm25_index = Mock(spec=IncrementalBM25)
        
        reloader = IncrementalReloader(
            corpus_dir=corpus_dir,
            manifest_path=manifest_path,
            faiss_index=faiss_index,
            bm25_index=bm25_index,
            embedding_function=Mock(),
            tokenizer_function=Mock(),
            domain_tagger_function=Mock()
        )
        
        # Should still complete (creates new manifest)
        result = None
        for item in reloader.reload(dry_run=True, stream_progress=False):
            if isinstance(item, ReloadResult):
                result = item
        
        assert result is not None
        # May have error about missing manifest, but operation continues
