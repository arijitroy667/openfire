# Connection pool capture demo

This tiny project reproduces a failing check and a fix. Copy this directory outside the EngBrain checkout before initializing Git so it becomes its own repository.

```powershell
Copy-Item -Recurse examples/demo-repo "$env:TEMP/engbrain-demo"
Set-Location "$env:TEMP/engbrain-demo"
git init
git add .
git -c user.name="Demo" -c user.email="demo@example.invalid" commit -m "demo fixture"
engbrain init --client claude-code
```

Run the exact same check twice:

```powershell
python scripts/check_pool.py
python scripts/check_pool.py
```

It fails with `Connection pool exhausted`. Increase `MAX_CONNECTIONS` in `src/pool_config.py` from `1` to `4`, then run the same command again. The third run passes. Claude Code's asynchronous hooks create a draft with the commands and exit codes; inspect it with `engbrain review`, then accept it with `engbrain review accept <id>`.

The fixture never stores a terminal transcript. The hook keeps only a redacted 2 KB output tail in the seven-day local event buffer; the episode exposes the normalized error signature and command evidence.
