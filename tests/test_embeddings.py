"""Unit tests for app/services/embeddings.py.

Cohere client is monkey-patched. Supabase calls that touch real DB are not
exercised here — those are smoke-tested separately in test_competitor_pipeline.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import embeddings as emb


passed = 0
failed = 0


def check(condition: bool, label: str) -> None:
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {label}")
    else:
        failed += 1
        print(f"  FAIL: {label}")


# ── text_hash ────────────────────────────────────────────────────────────────


def test_text_hash_normalisation():
    print("\n--- text_hash normalisation ---")
    h1 = emb.text_hash("Great service!")
    h2 = emb.text_hash("  great   service!  ")
    h3 = emb.text_hash("GREAT SERVICE!")
    check(h1 == h2 == h3, "whitespace + case normalised → same hash")
    check(h1 != emb.text_hash("bad service"), "different text → different hash")
    check(len(h1) == 64, "SHA-256 hex length is 64")


# ── cosine similarity ────────────────────────────────────────────────────────


def test_cosine_similarity():
    print("\n--- cosine_similarity ---")
    check(abs(emb.cosine_similarity([1, 0, 0], [1, 0, 0]) - 1.0) < 1e-9,
          "identical vectors → 1.0")
    check(abs(emb.cosine_similarity([1, 0, 0], [0, 1, 0])) < 1e-9,
          "orthogonal vectors → 0.0")
    check(abs(emb.cosine_similarity([1, 0, 0], [-1, 0, 0]) + 1.0) < 1e-9,
          "anti-parallel → -1.0")
    check(emb.cosine_similarity([], [1, 0, 0]) == 0.0,
          "empty input → 0.0 (no crash)")
    check(emb.cosine_similarity([0, 0, 0], [1, 0, 0]) == 0.0,
          "zero vector → 0.0 (no divide-by-zero)")
    check(emb.cosine_similarity([1, 0], [1, 0, 0]) == 0.0,
          "mismatched dims → 0.0 (no crash)")


# ── _build_centroid_text ─────────────────────────────────────────────────────


def test_build_centroid_text():
    print("\n--- _build_centroid_text ---")
    out = emb._build_centroid_text(["one", "two", "three"])
    check("one" in out and "two" in out and "three" in out, "all texts included")
    check(" || " in out, "joined with separator")
    check(emb._build_centroid_text([]) == "", "empty list → empty string")
    check(emb._build_centroid_text(["", "  ", None]) == "",
          "blank/None entries skipped")
    # Cap test
    long_list = [f"review {i}" for i in range(100)]
    capped = emb._build_centroid_text(long_list)
    check("review 0" in capped, "first review included")
    # MAX_REVIEWS_PER_COMPETITOR_FOR_EMBEDDING = 30, so review 50 shouldn't be there
    check("review 50" not in capped, "review past cap excluded")


# ── _parse_pgvector ──────────────────────────────────────────────────────────


def test_parse_pgvector():
    print("\n--- _parse_pgvector ---")
    out = emb._parse_pgvector("[1.0, 2.5, -0.3]")
    check(out == [1.0, 2.5, -0.3], "parses pgvector text format")
    check(emb._parse_pgvector("[]") == [], "empty vector parses to []")
    check(emb._parse_pgvector("") == [], "empty string parses to []")


# ── embed_texts with mocked Cohere ───────────────────────────────────────────


class _FakeCohereResponse:
    def __init__(self, n: int, dim: int = 1024):
        # Use i+1 so the first vector is non-zero — matches what real Cohere
        # would return (no embedding is exactly zero for non-empty text).
        self.embeddings = [[float(i + 1)] * dim for i in range(n)]


class _FakeCohereClient:
    def __init__(self):
        self.calls = []

    def embed(self, texts, model, input_type):
        self.calls.append({"texts": texts, "model": model, "input_type": input_type})
        return _FakeCohereResponse(len(texts), dim=emb.EMBEDDING_DIM)


def test_embed_texts_with_mock():
    print("\n--- embed_texts (mocked Cohere) ---")
    fake = _FakeCohereClient()
    emb._client = fake  # override the lazy client

    out = emb.embed_texts(["a", "b", "c"])
    check(len(out) == 3, "3 inputs → 3 outputs")
    check(all(len(v) == emb.EMBEDDING_DIM for v in out), "all vectors are correct dim")
    check(len(fake.calls) == 1, "one Cohere call for 3 texts (under batch limit)")

    # Empty input handling
    out2 = emb.embed_texts([])
    check(out2 == [], "empty input → empty output")

    # All-empty strings → zero vectors, no Cohere call
    fake.calls = []
    out3 = emb.embed_texts(["", "  "])
    check(len(out3) == 2, "2 blank inputs → 2 zero-vector outputs")
    check(all(all(x == 0.0 for x in v) for v in out3), "blanks become zero vectors")
    check(len(fake.calls) == 0, "no Cohere call for all-blank input")

    # Mixed: blank + real
    fake.calls = []
    out4 = emb.embed_texts(["", "real text"])
    check(len(out4) == 2, "mixed input → 2 outputs in order")
    check(all(x == 0.0 for x in out4[0]), "blank slot is zero vector")
    check(out4[1] != [0.0] * emb.EMBEDDING_DIM, "real-text slot is non-zero")
    check(len(fake.calls) == 1 and fake.calls[0]["texts"] == ["real text"],
          "Cohere only called with the non-blank text")

    emb._client = None  # reset so other tests get a fresh client


# ── rank_by_similarity ───────────────────────────────────────────────────────


def test_rank_by_similarity_orders_correctly(monkeypatch=None):
    print("\n--- rank_by_similarity ---")
    # Stub get_centroid so we don't hit Supabase.
    fake_centroids = {
        "near":  [1.0, 0.0, 0.0],
        "mid":   [0.7, 0.7, 0.0],
        "far":   [0.0, 1.0, 0.0],
        "missing": None,
    }
    orig = emb.get_centroid
    emb.get_centroid = lambda pid: fake_centroids.get(pid)

    try:
        my_centroid = [1.0, 0.0, 0.0]
        candidates = [
            {"place_id": "far", "name": "Far"},
            {"place_id": "near", "name": "Near"},
            {"place_id": "missing", "name": "Missing"},
            {"place_id": "mid", "name": "Mid"},
        ]
        ranked = emb.rank_by_similarity(my_centroid, candidates)
        names_in_order = [c["name"] for c in ranked]
        check(names_in_order[0] == "Near", f"Near is first (got {names_in_order[0]})")
        check(names_in_order[-1] == "Missing", f"Missing-centroid is last (got {names_in_order[-1]})")
        check(ranked[0]["similarity"] >= ranked[1]["similarity"] >= ranked[2]["similarity"],
              "scores are descending")
        check(ranked[-1]["similarity"] == 0.0, "missing centroid → similarity 0.0")
    finally:
        emb.get_centroid = orig


# ── Run ──────────────────────────────────────────────────────────────────────


def main():
    test_text_hash_normalisation()
    test_cosine_similarity()
    test_build_centroid_text()
    test_parse_pgvector()
    test_embed_texts_with_mock()
    test_rank_by_similarity_orders_correctly()

    print(f"\n{'=' * 50}")
    print(f"Total: {passed + failed}  |  Passed: {passed}  |  Failed: {failed}")
    print("=" * 50)
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
