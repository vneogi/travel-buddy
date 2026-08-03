"""Selects the persistence backend.

Defaults to the in-memory backend. When Supabase creds are configured the
Supabase backend is used instead. NOTE: the Supabase path has NOT been
validated against a live database yet — flip it on only after running the
schema/functions from models/database.py + supabase_service.ADDITIONAL_SQL_FUNCTIONS
and doing an integration test with real TB_SUPABASE_* creds.
"""
from services.database_service import db_service
from services.supabase_service import supabase_db

db = supabase_db if supabase_db is not None else db_service
