# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rules

1. Never use em dashes (U+2014) or emoji, in code, comments, strings, docstrings, commit messages or docs. Stick to plain ASCII punctuation: hyphens, commas, colons, parentheses.
2. Commits are authored by the user only. Never add a `Co-Authored-By: Claude` trailer or any other Claude/AI attribution line to commit messages or PR descriptions.
3. Commit messages follow Conventional Commits: `<type>(<optional scope>): <short summary>`, summary written in French (see rule 4), imperative/infinitive form, lowercase, no trailing period, under about 72 characters. The type keywords themselves stay in English. Types: `feat` (new feature/analysis), `fix` (bug fix), `data` (add or update datasets), `docs`, `refactor`, `perf`, `test`, `chore` (tooling, config, .gitignore), `style`, `build`, `ci`. Breaking changes use `!` after the type (e.g. `feat!: ...`). Example: `feat(backtest): ajouter le rebalancement mensuel avec conversion fx`.
4. Language: code is in English (variable, function, class, file and column names). Everything written for humans is in French: comments, docstrings, log/print messages, plot titles and labels, notebook markdown, docs and commit messages. French accents are fine; rule 1 only restricts punctuation and emoji.
5. Project layout: every new file goes in the folder matching its role below; never drop files at the root (the root holds only README.md, .gitignore, CLAUDE.md and dependency/config files such as requirements.txt or pyproject.toml). Create a new top-level folder only if no existing one fits, and add it to the structure section of the root README.md. Folder and file names are English, lowercase snake_case, descriptive (`fx_conversion.py`, not `utils2.py`); notebooks are numbered to show order (`01_exploration_prices.ipynb`). All paths in code are built relative to the project root (e.g. `Path(__file__).resolve().parents[n]`), never absolute or dependent on the working directory.

| Folder | Holds |
| --- | --- |
| `data/raw/` | Organizer starter data. Read-only: never edit by hand, only `scripts/build_dataset.py` writes here. |
| `data/external/` | Data the team adds. Every new source gets an entry (source, URL, retrieval date, processing, limitations) in `data/external/sources.md`. |
| `data/processed/` | Cleaned/aligned data produced by code. Git-ignored, must be reproducible from code. |
| `src/alphaforge/` | Reusable Python package: loading, alignment, strategies, metrics. Notebooks and scripts import from here instead of duplicating logic. |
| `scripts/` | Command-line entry points (data download, pipelines, report generation). |
| `notebooks/` | Exploration and analysis. Keep heavy logic in `src/`. |
| `outputs/figures/`, `outputs/reports/` | Generated charts and tables for the final presentation. |
| `docs/` | Project documentation, methodology, presentation material. |
| `tests/` | Tests for `src/alphaforge/`, mirroring its module names (`test_<module>.py`). |

## What this is

Starter dataset for the PolyFinances **AlphaForge AI** datathon (2026). It is simulation material only, not investment advice. The case brief and organizer slides live outside the repo, one level up (`../Datathon - Case Officiel 2026 ENG.pdf` / `FR.pdf`, `../Presentation_AlphaForge_AI_Participants - EN V2.pptx`). The brief refers to personas (Mateo: ESG/energy screening; Robert: volatile high-profile names like TSLA and NVDA; Amira: crypto plus non-tech growth) that the universe was chosen to serve.

The organizers say this pack is a starting point, not the expected dataset. Teams may add or replace data, but every added source must be documented: source, retrieval date and processing.

## Commands

Run everything from the project root. The only code so far is `scripts/build_dataset.py`. It downloads everything again from the network and overwrites all generated files in `data/raw/`. On Windows the venv binaries are under `.venv/Scripts/`:

```bash
python -m venv .venv
.venv/Scripts/pip install pandas yfinance      # .venv/bin/... on macOS/Linux
.venv/Scripts/python scripts/build_dataset.py
```

There are no tests, linter or build step. `check()` in the script is the validation: it hard-fails on duplicate `(date, ticker)` rows, missing tickers, currency mismatches or non-positive `adj_close`, and writes soft warnings (late start, early end, gaps, one-day moves above 40%) to `data_quality_warnings.txt`.

Rebuilding is destructive. `adj_close` is back-adjusted from the latest date, so a re-download changes historical values. Don't re-run it unless asked.

## Data pipeline (`scripts/build_dataset.py`)

- Config at the top: `START`, `END` (inclusive; the script adds one day for yfinance's exclusive end), `UNIVERSE` (ticker tuples; `asset_id` A01..A31 comes from list order), `BOC_SERIES`, `FRED_SERIES`.
- `build_prices` produces `prices_daily.csv` + `corporate_actions.csv` (one `yf.download` with `auto_adjust=False, actions=True`).
- `build_macro` produces `fx_usdcad_daily.csv` (BoC `FXUSDCAD`, kept separate) + `macro_rates.csv` (long format: other BoC Valet series + FRED CSV endpoint).
- Output directory is `OUT_DIR` = `data/raw/` (resolved from the script location).
- `data/raw/README.md` (organizer dataset doc) and `data/raw/sources_metadata.csv` are hand-written and **not** regenerated. Update them by hand if the universe, window or sources change.

## Data pitfalls (affect any analysis/backtest code)

- **Currencies:** `.TO` tickers are CAD, everything else USD. Convert with `fx_usdcad_daily.csv`, which has no rows on Canadian holidays (forward-fill the rate).
- **No calendar alignment or forward-fill:** rows exist only on days Yahoo reports a price. TSX and US holidays differ, and crypto trades 7 days a week (1,827 rows vs about 1,255 for equities). Align calendars explicitly and document how.
- Use `adj_close` for returns (split + dividend adjusted). `close` is split-adjusted only. Split rows in `corporate_actions.csv` are reference only; never apply them again.
- CNQ.TO has a spurious 1.021 "split" on 2022-08-22 (likely a special distribution).
- Crypto rows are UTC calendar days; there is no market close.
- Monthly macro (CPI, UNRATE) is dated to the reference month, not the release date. Lag it in backtests to avoid look-ahead. FRED values are revised figures, not first releases.
- Survivorship bias: the universe was picked in 2026 from names that are large today.
- No ESG scores, news or fundamentals are included. Those need external, documented sources (sustainability reports, SEDAR+, EDGAR, ETF issuer methodology pages).
