from threading import local
from typing import Any

from supabase import create_client
from app.config import SUPABASE_URL, SUPABASE_KEY


_state = local()


def get_supabase() -> Any:
    """Return a Supabase client scoped to the current worker thread.

    FastAPI runs sync endpoints in a threadpool. Reusing one global Supabase
    client shares the underlying httpx session across concurrent requests,
    which can surface as intermittent "deque mutated" / disconnect errors.
    """
    client = getattr(_state, "client", None)
    if client is None:
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        _state.client = client
    return client


class SupabaseProxy:
    """Backwards-compatible proxy for existing `supabase.table(...)` imports."""

    def __getattr__(self, name: str) -> Any:
        return getattr(get_supabase(), name)


supabase = SupabaseProxy()
