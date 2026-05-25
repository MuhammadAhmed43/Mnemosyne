# Contributing to Mnemosyne

Thanks for your interest in improving Mnemosyne! This project is local-first,
privacy-focused, and built to be hacked on. Contributions of all sizes are welcome.

## Ways to contribute

- 🐛 **Report a bug** or 💡 **request a feature** via [Issues](../../issues).
- 🧪 **Improve extraction quality** — the highest-leverage contribution (see below).
- 📝 **Docs & examples** — clarity wins.
- 🔌 **New platform selectors** — keep capture working as Claude/ChatGPT/Gemini change.

## Project layout

```
backend/      # Python engine (FastAPI) — extraction, storage, retrieval, API
extension/    # Chrome MV3 extension (TypeScript + React + Plasmo)
tests/        # pytest suites + the extraction eval harness (tests/eval)
```

## Local setup

**Engine**

```bash
python -m venv .venv && . .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"                          # deps + spaCy model + dev tools
mnemosyne-engine                                 # http://localhost:7432
```

**Extension**

```bash
cd extension
npm install
npm run build:chrome     # load extension/build/chrome-mv3-prod as unpacked
```

## Before you open a PR

Run everything green:

```bash
ruff check backend/                              # lint
pytest -q                                        # backend tests + extraction eval
python tests/eval/test_extraction_quality.py     # extraction quality report
cd extension && node node_modules/typescript/bin/tsc --noEmit && npm test
```

## The golden rule for extraction changes

Extraction quality is **measured, not guessed**. If you hit a conversation turn that
extracts badly:

1. Add a labeled case to [`tests/eval/cases.py`](tests/eval/cases.py) describing what
   *should* (and shouldn't) be extracted.
2. Run the eval — watch your case fail.
3. Fix the pipeline until it passes.
4. The eval gate (`pytest tests/eval/`) ensures it never regresses.

This is how we keep precision/recall from drifting. Every fix becomes a permanent test.

## Commit style

We use [Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`,
`docs:`, `test:`, `refactor:`, `chore:`, with an optional scope (`feat(extraction): …`).

## Code style

- **Python:** `ruff` (configured in `pyproject.toml`), type hints encouraged.
- **TypeScript:** strict mode; keep `tsc --noEmit` clean.
- Prefer small, focused PRs with a clear description of the *why*.

By contributing, you agree your contributions are licensed under the [MIT License](LICENSE).
