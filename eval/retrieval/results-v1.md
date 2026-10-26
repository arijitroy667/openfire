# Retrieval challenge results — 2026-10-26

## Setup

The lexical-only production retriever was evaluated against 12 target episodes, 30 distractors, and 36 queries. The set contains five simplified public-issue reproductions and seven synthetic incidents. Each incident has a lexical query, a separately worded paraphrase, and a symptom-oriented query.

## Results

| Query type | n | Recall@5 | MRR | Precision@5 |
| --- | ---: | ---: | ---: | ---: |
| Lexical | 12 | 1.000 | 1.000 | 0.200 |
| Paraphrase | 12 | 1.000 | 0.903 | 0.200 |
| Symptom | 12 | 1.000 | 0.861 | 0.200 |

All 15 queries for public-issue reproductions and all 21 queries for synthetic incidents retrieved their target within the first five. The combined local p95 search latency was 38.707 ms over 36 calls.

## Decision and limitations

The v1.1 PRD's initial paraphrase Recall@5 threshold is 0.70. This challenge scored 1.00 on paraphrase Recall@5, so the results do not justify adding embeddings now. Embeddings remain deferred; a larger set of independent incidents and full upstream repositories could change that decision.

This is a narrow query challenge. The incident targets are reused from the Codex fixture corpus, five public issues are represented by small dependency-free reproductions, and 12 examples cannot represent all codebases or user phrasing. The challenge should be expanded before drawing broad retrieval-quality conclusions. Do not use this result as evidence that EngBrain reduces agent failures.
