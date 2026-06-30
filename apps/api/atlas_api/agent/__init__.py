"""ATLAS chat agent — grounded natural-language Q&A over the real EOD store.

The LLM (or the deterministic fallback) never invents numbers: every figure it
reports comes back from a tool in ``tools.py`` that queries the same SQLite store
the REST endpoints use. Honesty rule holds — analysis, not profecia.
"""
