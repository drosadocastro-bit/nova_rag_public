from pathlib import Path
from datetime import datetime
import json
import pickle
from typing import Optional, Any, Callable
from .index_version import IndexVersion


class VersionedCacheManager: 
    """Manages cached indices with automatic version detection and rebuilding."""
    
    def __init__(self, cache_dir: str = "./cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir. mkdir(exist_ok=True, parents=True)
    
    def get_index(
        self,
        name: str,
        current_version: IndexVersion,
        builder_fn: Callable[[], Any],
        namespace: str = "retrieval"
    ) -> Any:
        """
        Get cached index or rebuild if version mismatch. 
        
        Args:
            name: Index identifier (e.g., 'bm25', 'faiss')
            current_version: Expected index version
            builder_fn: Function to call if rebuild needed
            namespace: Cache namespace (subdirectory)
            
        Returns:
            Loaded or newly built index
        """
        namespace_dir = self.cache_dir / namespace
        namespace_dir.mkdir(exist_ok=True, parents=True)
        
        cache_path = namespace_dir / f"{name}_index. pkl"
        version_path = namespace_dir / f"{name}_version.json"
        
        # Try to load cached index
        if cache_path. exists() and version_path.exists():
            try:
                with open(version_path, 'r') as f:
                    cached_version = IndexVersion.from_dict(json. load(f))
                
                if current_version.is_compatible_with(cached_version):
                    print(f"✓ Loading cached {name} index (fingerprint: {cached_version.compute_fingerprint()})")
                    with open(cache_path, 'rb') as f:
                        return pickle.load(f)
                else:
                    print(f"⚠ Version mismatch for {name} index:")
                    print(f"  Cached:   {cached_version.compute_fingerprint()}")
                    print(f"  Current: {current_version.compute_fingerprint()}")
                    self._archive_old_index(name, cached_version, namespace)
            except Exception as e:
                print(f"⚠ Failed to load cached {name} index: {e}")
        
        # Build new index
        print(f"⚙ Building {name} index...")
        index = builder_fn()
        
        # Save with version metadata
        current_version. created_at = datetime.utcnow().isoformat()
        with open(cache_path, 'wb') as f:
            pickle.dump(index, f)
        with open(version_path, 'w') as f:
            json.dump(current_version.to_dict(), f, indent=2)
        
        print(f"✓ Index cached (fingerprint: {current_version.compute_fingerprint()})")
        return index
    
    def _archive_old_index(self, name: str, old_version: IndexVersion, namespace:  str):
        """Move old index to archive directory."""
        archive_dir = self.cache_dir / "archive"
        archive_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fingerprint = old_version.compute_fingerprint()
        
        old_cache = self.cache_dir / namespace / f"{name}_index.pkl"
        if old_cache.exists():
            archive_path = archive_dir / f"{name}_{fingerprint}_{timestamp}.pkl"
            old_cache.rename(archive_path)
            print(f"  Archived old index:  {archive_path. name}")
    
    def clear(self, namespace: Optional[str] = None):
        """Clear cache files (optionally by namespace)."""
        if namespace:
            target = self.cache_dir / namespace
        else:
            target = self.cache_dir
        
        if target.exists():
            for pkl_file in target.glob("**/*.pkl"):
                pkl_file.unlink()
            print(f"✓ Cleared cache:  {target}")