"""
Phase 3 Integration Example: End-to-End Incremental Indexing

This example demonstrates the complete Phase 3 incremental indexing workflow:
1. Initialize incremental components
2. Detect corpus changes
3. Add new documents without server restart
4. Validate hot-reload functionality

Usage:
    python examples/phase3_integration.py
"""

import logging
from pathlib import Path
import numpy as np

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def example_incremental_indexing():
    """
    Demonstrate incremental indexing workflow.
    """
    from core.indexing import (
        CorpusManifest,
        IncrementalFAISSIndex,
        IncrementalBM25,
        BM25Document,
        IncrementalReloader,
        detect_changes,
        get_next_chunk_id,
    )
    
    # Setup paths
    base_dir = Path("vector_db/phase3_example")
    base_dir.mkdir(parents=True, exist_ok=True)
    
    corpus_dir = Path("data/manuals")
    manifest_path = base_dir / "corpus_manifest.json"
    faiss_path = base_dir / "faiss.index"
    bm25_path = base_dir / "bm25_corpus.pkl"
    
    logger.info("=" * 60)
    logger.info("Phase 3 Incremental Indexing Example")
    logger.info("=" * 60)
    
    # Step 1: Initialize components
    logger.info("\n[Step 1] Initializing incremental components...")
    
    manifest = CorpusManifest.load(manifest_path)
    faiss_index = IncrementalFAISSIndex(dimension=384, index_path=faiss_path)
    bm25_index = IncrementalBM25(corpus_path=bm25_path)
    
    logger.info(f"✓ Manifest: {manifest.total_chunks} chunks in {len(manifest.files)} files")
    logger.info(f"✓ FAISS: {faiss_index.total_vectors} vectors")
    logger.info(f"✓ BM25: {bm25_index.total_documents} documents")
    
    # Step 2: Detect changes
    logger.info("\n[Step 2] Detecting corpus changes...")
    
    changes = detect_changes(corpus_dir, manifest)
    new_files = [c for c in changes if c.change_type.value == "new"]
    modified_files = [c for c in changes if c.change_type.value == "modified"]
    
    logger.info(f"✓ Found {len(new_files)} new files")
    logger.info(f"✓ Found {len(modified_files)} modified files")
    
    if not new_files and not modified_files:
        logger.info("  → No changes detected. Corpus is up to date.")
        return
    
    # Step 3: Add new documents
    logger.info("\n[Step 3] Adding new documents...")
    
    for change in new_files[:3]:  # Process first 3 files as example
        logger.info(f"\n  Processing: {change.file_path}")
        
        # Simulate document ingestion (in real system, use full pipeline)
        example_chunks = [
            f"Example chunk {i} from {change.file_path}"
            for i in range(5)
        ]
        
        # Generate example embeddings (in real system, use embedding model)
        embeddings = np.random.rand(len(example_chunks), 384).astype('float32')
        
        # Generate example tokens (in real system, use tokenizer)
        tokens = [
            ["example", "chunk", str(i), "test"]
            for i in range(len(example_chunks))
        ]
        
        # Get chunk IDs
        start_id = get_next_chunk_id(manifest)
        chunk_ids = list(range(start_id, start_id + len(example_chunks)))
        
        # Add to FAISS
        success, error = faiss_index.add_chunks(embeddings, chunk_ids)
        if success:
            logger.info(f"    ✓ Added {len(chunk_ids)} embeddings to FAISS")
        else:
            logger.error(f"    ✗ FAISS error: {error}")
            continue
        
        # Add to BM25
        bm25_docs = [
            BM25Document(
                chunk_id=chunk_ids[i],
                tokens=tokens[i],
                domain="example_domain",
                metadata={"file": change.file_path}
            )
            for i in range(len(example_chunks))
        ]
        success, error = bm25_index.add_documents(bm25_docs)
        if success:
            logger.info(f"    ✓ Added {len(bm25_docs)} documents to BM25")
        else:
            logger.error(f"    ✗ BM25 error: {error}")
            continue
        
        # Update manifest
        manifest.add_file(
            file_path=change.file_path,
            sha256=change.new_hash or "",
            chunk_count=len(example_chunks),
            chunk_ids=chunk_ids,
            domain="example_domain"
        )
        logger.info(f"    ✓ Updated manifest")
    
    # Step 4: Save state
    logger.info("\n[Step 4] Saving updated indices...")
    
    manifest.save(manifest_path)
    faiss_index.save()
    # BM25 auto-saves
    
    logger.info("✓ All indices saved")
    
    # Step 5: Verify
    logger.info("\n[Step 5] Verification...")
    
    logger.info(f"✓ Final manifest: {manifest.total_chunks} chunks in {len(manifest.files)} files")
    logger.info(f"✓ Final FAISS: {faiss_index.total_vectors} vectors")
    logger.info(f"✓ Final BM25: {bm25_index.total_documents} documents")
    
    # Get statistics
    faiss_stats = faiss_index.get_stats()
    bm25_stats = bm25_index.get_stats()
    
    logger.info("\nFAISS Stats:")
    logger.info(f"  - Index type: {faiss_stats['index_type']}")
    logger.info(f"  - Dimension: {faiss_stats['dimension']}")
    logger.info(f"  - Backups: {faiss_stats['backup_count']}")
    
    logger.info("\nBM25 Stats:")
    logger.info(f"  - Parameters: k1={bm25_stats['params']['k1']}, b={bm25_stats['params']['b']}")
    logger.info(f"  - Domain distribution: {bm25_stats['domain_distribution']}")
    
    logger.info("\n" + "=" * 60)
    logger.info("✓ Phase 3 incremental indexing complete!")
    logger.info("=" * 60)


def example_hot_reload_api():
    """
    Demonstrate hot-reload API usage.
    """
    logger.info("\n\n" + "=" * 60)
    logger.info("Hot-Reload API Example")
    logger.info("=" * 60)
    
    logger.info("\nTo use the hot-reload API in production:")
    logger.info("\n1. Dry-run mode (detect changes without applying):")
    logger.info("   curl -X POST 'http://localhost:5000/api/reload?dry_run=true'")
    
    logger.info("\n2. Apply changes:")
    logger.info("   curl -X POST 'http://localhost:5000/api/reload'")
    
    logger.info("\n3. Stream progress updates:")
    logger.info("   curl -X POST 'http://localhost:5000/api/reload?stream=true'")
    
    logger.info("\n4. Example response:")
    logger.info("""
    {
      "success": true,
      "dry_run": false,
      "files_added": 3,
      "files_modified": 1,
      "files_deleted": 0,
      "chunks_added": 150,
      "duration_seconds": 2.3,
      "errors": [],
      "manifest_path": "vector_db/corpus_manifest.json",
      "timestamp": "2026-01-22T10:30:00Z"
    }
    """)


if __name__ == "__main__":
    try:
        example_incremental_indexing()
        example_hot_reload_api()
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        logger.info("\nInstall required packages:")
        logger.info("  pip install faiss-cpu rank-bm25 numpy")
    except Exception as e:
        logger.error(f"Error during example: {e}", exc_info=True)
