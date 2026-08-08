"""File ingestion and retrieval for study materials and homework.

The pipeline is deliberately split into swappable seams:

    upload → FileStorage        (where the bytes live)
           → DocumentExtractor  (bytes → plain text)
           → chunk_text         (text → retrievable slices)
           → MaterialRetriever  (query → only the relevant slices)

Each stage is an interface with one working implementation today, so local disk
can become object storage, and keyword ranking can become vector search, without
touching the service or API layers.
"""
