\# Cache Architecture



\## Overview



Nova uses a versioned cache system that automatically rebuilds indices when configuration changes. 



\## Directory Structure



```

cache/

├── retrieval/          # BM25 and embedding indices

│   ├── bm25\_index.pkl

│   ├── bm25\_version.json

│   └── query\_cache.pkl

├── sessions/           # User session data

└── archive/            # Old indices (timestamped)

```



\## Version Tracking



Each index has an associated `\*\_version.json` file that tracks:

\- Schema version

\- Embedding model

\- Chunking parameters

\- BM25 parameters  

\- Corpus hash



When any parameter changes, the index automatically rebuilds.



\## Usage Example



```python

from core.caching.cache_manager import VersionedCacheManager

from core.caching.index_version import IndexVersion

import hashlib



\# Initialize cache manager

cache = VersionedCacheManager()



\# Define current index version

version = IndexVersion(

&nbsp;   schema\_version="1.0.0",

&nbsp;   embedding\_model="all-MiniLM-L6-v2",

&nbsp;   chunk\_size=512,

&nbsp;   bm25\_k1=1.5,

&nbsp;   bm25\_b=0.75,

&nbsp;   corpus\_hash=hashlib.sha256(corpus\_data. encode()).hexdigest()\[:16]

)



\# Get index (loads cached or rebuilds if version mismatch)

def build\_my\_index():

&nbsp;   # Your index building logic

&nbsp;   return my\_index



index = cache.get\_index(

&nbsp;   name="bm25",

&nbsp;   current\_version=version,

&nbsp;   builder\_fn=build\_my\_index,

&nbsp;   namespace="retrieval"

)

```



\## Cache Management



```python

\# Clear all caches

cache.clear()



\# Clear specific namespace

cache.clear("retrieval")

```



\## Benefits



1\. \*\*Automatic Rebuilds\*\*: No manual cache clearing needed

2\. \*\*Version History\*\*: Archive system preserves old indices

3\. \*\*Git-Friendly\*\*: Version metadata (JSON) is tracked, binary files are not

4\. \*\*Reproducibility\*\*: Exact configuration is recorded with each index

5\. \*\*Safe Upgrades\*\*: Old indices archived before rebuild (can be restored)

```

