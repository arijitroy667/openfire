from __future__ import annotations

import json

import pytest

from engbrain.evaluation import run_retrieval_evaluation


def test_bundled_demo_corpus_reports_retrieval_metrics():
    result = run_retrieval_evaluation()
    assert result["corpus_kind"] == "synthetic_demo"
    assert result["target_episodes"] == 12
    assert result["distractor_episodes"] == 30
    assert result["query_count"] == 24
    assert set(result["retrieval_metrics"]) == {"lexical", "paraphrase"}
    assert result["retrieval_metrics"]["lexical"]["n"] == 12
    assert result["latency_ms"]["p95"] >= 0


def test_custom_corpus_validation_rejects_missing_target_fields(tmp_path):
    corpus_path = tmp_path / "corpus.json"
    corpus_path.write_text(
        json.dumps({"targets": [{"id": "broken", "queries": {"lexical": "some query"}}], "distractors": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="title"):
        run_retrieval_evaluation(corpus_path)
