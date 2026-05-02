from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import history


class FakeSupabase:
    def __init__(
        self,
        *,
        business_rows=None,
        score_rows=None,
        business_failures: int = 0,
        score_failures: int = 0,
    ) -> None:
        self.business_rows = [{"id": "biz_1"}] if business_rows is None else business_rows
        self.score_rows = score_rows or []
        self.business_failures = business_failures
        self.score_failures = score_failures
        self.business_calls = 0
        self.score_calls = 0

    def table(self, name: str) -> "FakeQuery":
        return FakeQuery(self, name)


class FakeQuery:
    def __init__(self, db: FakeSupabase, table_name: str) -> None:
        self.db = db
        self.table_name = table_name

    def select(self, *_args, **_kwargs) -> "FakeQuery":
        return self

    def eq(self, *_args, **_kwargs) -> "FakeQuery":
        return self

    def order(self, *_args, **_kwargs) -> "FakeQuery":
        return self

    def limit(self, *_args, **_kwargs) -> "FakeQuery":
        return self

    def execute(self) -> SimpleNamespace:
        if self.table_name == "businesses":
            self.db.business_calls += 1
            if self.db.business_failures:
                self.db.business_failures -= 1
                raise RuntimeError("Server disconnected")
            return SimpleNamespace(data=self.db.business_rows)

        if self.table_name == "health_scores":
            self.db.score_calls += 1
            if self.db.score_failures:
                self.db.score_failures -= 1
                raise RuntimeError("Server disconnected")
            return SimpleNamespace(data=self.db.score_rows)

        raise AssertionError(f"Unexpected table: {self.table_name}")


def _score_row(**overrides) -> dict:
    row = {
        "final_score": 72,
        "review_score": 70,
        "competitor_score": 65,
        "pos_score": 80,
        "google_rating": 4.2,
        "insights": ["first", "second", "third"],
        "action": "Do the useful thing",
        "created_at": "2026-04-30T12:00:00+00:00",
    }
    row.update(overrides)
    return row


def test_history_retries_transient_score_query(monkeypatch):
    fake = FakeSupabase(score_rows=[_score_row()], score_failures=1)
    monkeypatch.setattr(history, "supabase", fake)
    monkeypatch.setattr(history.time, "sleep", lambda _seconds: None)

    response = history.get_history("biz_1")

    assert response.count == 1
    assert response.scores[0].final_score == 72
    assert fake.score_calls == 2


def test_history_returns_empty_when_business_lookup_disconnects(monkeypatch):
    fake = FakeSupabase(business_failures=2)
    monkeypatch.setattr(history, "supabase", fake)
    monkeypatch.setattr(history.time, "sleep", lambda _seconds: None)

    response = history.get_history("biz_1")

    assert response.count == 0
    assert response.scores == []
    assert fake.business_calls == history.MAX_DB_ATTEMPTS


def test_history_still_404s_when_business_is_absent(monkeypatch):
    fake = FakeSupabase(business_rows=[])
    monkeypatch.setattr(history, "supabase", fake)

    with pytest.raises(HTTPException) as exc:
        history.get_history("missing")

    assert exc.value.status_code == 404
