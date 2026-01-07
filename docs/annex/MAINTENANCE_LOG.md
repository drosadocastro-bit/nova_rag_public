# Maintenance Log

Status: Current corpus and terminology are vehicle-maintenance only.

Highlights
----------
- Paths normalized to C:\nova_rag_public and vehicle data locations.
- Legacy domain wording removed; prompts and UI are domain-neutral.
- Index, docs, and embeddings aligned to vehicle_manual.txt under vector_db/.
- Safety comments now domain-agnostic (removed regulatory body references).

Notes
-----
- Keep citation strict mode enabled for safety-critical responses.
- For other domains, swap corpora and rebuild the FAISS index.
- Vehicle components recognized: engine, transmission, brakes, cooling, electrical, fuel, etc.
