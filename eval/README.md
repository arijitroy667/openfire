# Retrieval evaluation

Run the bundled fixture from a checkout with the package installed:

~~~powershell
uv run engbrain eval
uv run engbrain eval --json
~~~

The runner creates an isolated temporary Git repository and database. It seeds accepted target episodes and distractors, runs each query through the production retrieval function, and removes the temporary directory when finished. It does not call an LLM or network service.

## Bundled corpus and results

The bundled fixture contains 12 synthetic target episodes, 30 synthetic distractors, and 24 queries: one lexical and one paraphrase query per target. It is designed to make ranking behavior reproducible, not to represent real repositories.

The local release run returned:

| Query set | n | Recall@5 | MRR | Precision@5 |
| --- | ---: | ---: | ---: | ---: |
| Lexical | 12 | 1.000 | 1.000 | 0.200 |
| Paraphrase | 12 | 0.750 | 0.542 | 0.150 |

Latency is a local p95 measurement and varies by machine. These synthetic results do not establish public-issue retrieval quality, agent behavior, or reduced repeated attempts.

## Custom corpus format

Pass a JSON file with the same top-level structure:

~~~json
{
  "name": "my-retrieval-set",
  "kind": "custom",
  "notice": "Describe source, split, and limitations.",
  "targets": [
    {
      "id": "incident-1",
      "title": "Pool exhaustion",
      "type": "debugging",
      "problem": "Concurrent requests exhausted the connection pool.",
      "queries": {
        "lexical": "connection pool exhausted by concurrent requests",
        "paraphrase": "workers could not obtain a database connection"
      }
    }
  ],
  "distractors": [
    {
      "title": "Unrelated timeout",
      "type": "debugging",
      "problem": "The upstream service timed out before returning a response."
    }
  ]
}
~~~

Targets need a unique id, title, problem, and a non-empty queries object. Each query type is reported separately. Distractors need a title and problem. Optional target and distractor type values must match an EngBrain episode type.

## Metrics

- **Recall@5:** fraction of queries whose matching target appears in the first five results.
- **MRR:** mean reciprocal rank of the matching target, with a zero for misses outside the first five.
- **Precision@5:** number of matching targets in the first five divided by five result slots per query. There is one relevant target per query, so the maximum is 0.2.
- **p95 latency:** nearest-rank 95th percentile over individual local retrieval calls.

The current runner evaluates all bundled targets together. It does not implement the PRD's public-issue/dev-test split, launch coding-agent runs, or parse transcripts. Do not tune retrieval weights against a test set and describe those scores as held-out results.
