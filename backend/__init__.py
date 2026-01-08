"""
NovaRAG Backend - Public API exports.
Maintains backward compatibility with original monolithic backend.py.

This module provides a clean interface by re-exporting components from 
the refactored modules while maintaining full backward compatibility.
"""

# For now, we'll import from the original backend module and gradually migrate
# The extraction modules are ready but we need to update backend.py first

#  Import everything from original backend for now to maintain compatibility
import sys
from pathlib import Path

# Ensure parent directory is in path
_parent = Path(__file__).parent.parent.resolve()
if str(_parent) not in sys.path:
    sys.path.insert(0, str(_parent))

# Import original backend - this will be gradually replaced
import backend as _original_backend

# Re-export everything from original backend for backward compatibility
# As we migrate, we'll replace these with imports from the new modules
__all__ = [
    # Retrieval
    'build_index',
    'load_index', 
    'retrieve',
    'bm25_retrieve',
    'lexical_retrieve',
    'detect_error_code',
    '_boost_error_docs',
    'ERROR_CODE_TO_DOCS',
    'split_text',
    'split_text_semantic',
    'load_pdf_text',
    'load_pdf_text_with_pages',
    # Session Management
    'session_state',
    'reset_session',
    'start_new_session',
    'resume_session',
    'export_session_to_text',
    'save_session_report',
    'build_conversation_context',
    'TROUBLESHOOT_TRIGGERS',
    'END_SESSION_TRIGGERS',
    # Prompt Building
    'build_standard_prompt',
    'build_session_prompt',
    'choose_model',
    'suggest_keywords',
    'LLM_LLAMA',
    'LLM_OSS',
    'get_max_tokens',
    'DEEP_KEYWORDS',
    'FAST_KEYWORDS',
    'COMMON_SUBSYSTEMS',
    # LLM Client
    'call_llm',
    'check_ollama_connection',
    'ensure_model_loaded',
    'resolve_model_name',
    'OLLAMA_TIMEOUT_S',
    'OLLAMA_MODEL_LOAD_TIMEOUT_S',
    'USE_NATIVE_ENGINE',
    # Models and other components
    'get_text_embed_model',
    'get_cross_encoder',
    'ensure_vision_loaded',
    'nova_text_handler',
    'vision_search',
    'SearchHistory',
    'search_history',
    'index',
    'docs',
    'vision_model',
    'vision_embeddings',
    'vision_paths',
    'sklearn_reranker',
    'USE_SKLEARN_RERANKER',
    'list_recent_sessions',
]

# Create module-level references for everything
def __getattr__(name):
    """Dynamic attribute access for backward compatibility."""
    if hasattr(_original_backend, name):
        return getattr(_original_backend, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
