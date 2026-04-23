Run a syntax check on all key Python files and report any errors.

```bash
cd /Users/shashankreddyganta/Documents/btc-ai-agent && python3 -m py_compile \
  btc_agent/config.py \
  btc_agent/trading/scanner.py \
  btc_agent/trading/firestore_store.py \
  btc_agent/trading/executor.py \
  btc_agent/web/app.py \
  btc_agent/web/auth.py && echo "✓ All files OK"
```

Fix any syntax errors found before proceeding.
