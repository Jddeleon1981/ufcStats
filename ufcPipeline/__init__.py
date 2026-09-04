"""Shared helpers for the UFC stats ETL pipeline.

Both the one-time bulk load (``SQL/sqlCreate/tableSetup.py``) and the weekly
incremental Lambda (``SQL/sqlUpdate/ufcDBLambda.py``) import their scraping,
parsing, and database helpers from here so there is a single source of truth.
"""
