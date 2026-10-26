# Retrieval challenge set v1

`holdout-v1.json` pairs the existing 12 incident memories with 36 newly written queries: lexical, paraphrase, and symptom phrasings. Five targets are simplified reproductions based on public issues; seven are synthetic. Thirty distractors come from the bundled demo corpus.

Regenerate the fixed corpus and run it with:

~~~powershell
uv run python eval/retrieval/build_holdout.py
uv run engbrain eval --dataset eval/retrieval/holdout-v1.json --json
~~~

The query phrasings are frozen in `build_holdout.py`. Do not tune retrieval weights against these scores and continue calling them held out. The target incident set is shared with the earlier Codex fixtures, so this is an independent query challenge, not an independent sample of incidents or full upstream repositories. Results and interpretation are in [results-v1.md](results-v1.md).
