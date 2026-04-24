"""
test_connections.py — verify Supabase connectivity.
Run: python tests/test_connections.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import supabase

result = supabase.table("businesses").select("*").execute()
print("Supabase OK:", result.data)
