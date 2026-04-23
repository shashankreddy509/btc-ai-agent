When committing changes to this project:

1. Run syntax check first: `python3 -m py_compile btc_agent/trading/scanner.py btc_agent/web/app.py`
2. Run tests: `.venv/bin/python -m pytest tests/ -v --tb=short`
3. Only commit if both pass
4. Never commit: `.env`, `serviceAccountKey.json`, `*.pyc`, `__pycache__/`
5. Commit message format: imperative mood, present tense ("Add X", "Fix Y", "Remove Z")
6. Co-author line: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`
