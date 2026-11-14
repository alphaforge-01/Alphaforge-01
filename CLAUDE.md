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

6. Secrets: never put AWS credentials (access key IDs `AKIA...`/`ASIA...`, secret keys, session tokens) or any other secret (API keys, passwords, tokens) in the repo: not in code, notebooks (including cell outputs), config files, docs, commit messages or test fixtures, not even temporarily or as "example" values. A key pushed to GitHub is considered compromised within minutes. Credentials come only from outside the repo: AWS CLI profiles (`~/.aws/`, `aws configure` / `aws sso login`), environment variables, a git-ignored `.env`, or IAM roles when running on AWS. Code reads them via boto3's default credential chain or `os.environ`, never hard-coded. Before every commit, check the staged diff for secrets; if one is found, stop and tell the user. If a secret was ever committed or pushed, tell the user to revoke/rotate it in AWS immediately: deleting it in a later commit or rewriting history is not enough.

## What this is

Team project for the PolyFinances **AlphaForge AI** datathon (2026, sponsors: Banque Nationale and AWS). Simulation only, not investment advice. The repo currently holds the organizer starter dataset; the solution itself is still to be built. The case brief and organizer slides live outside the repo, one level up (`../Datathon - Case Officiel 2026 ENG.pdf` / `FR.pdf`, `../Presentation_AlphaForge_AI_Participants - EN V2.pptx`).

## The challenge (summary of the official brief)

Build a **self-explaining agentic solution** that uses public financial data to inform an investment decision, adapted to the investor's profile. One or more agents gather data, use tools, coordinate tasks and adapt to context. The output is free: asset comparison, scenario analysis, risk explanation, fictional allocation, decision aid. The goal is **not** the best-performing portfolio: the jury wants a credible, innovative, useful approach. A simple, focused, verifiable design is explicitly preferred over sophistication or many agents.

### Personas (fictional reference cases, and what each one tests)

| Persona | Risk / horizon | Profile and preferences | What the system must show |
| --- | --- | --- | --- |
| **Amira**, 26, software engineer | High / 15+ years | Single, intermediate experience. Long-term growth. Loves AI and emerging tech, open to high-growth and high volatility, interested in crypto, but wants some diversification and not an all-tech bet. | Where does risk acceptance stop? "High risk" must not mean "anything goes"; keep diversification consistent with her preferences. |
| **Mateo**, 41, operations manager | Moderate / 8-12 years | Partner, two kids, intermediate experience. Balanced growth. Strong ESG weight, avoid companies with major environmental or social controversies, balance growth and stability, open to emerging tech if it fits his risk, little interest in speculative assets. | Integrate non-financial preferences, not just return and risk. |
| **Robert**, 59, health professional | Low to moderate / 3-5 years | Married, adult kids, retiring soon, advanced experience. Preserve capital with some growth. Prefers established companies with business models he understands, values stability and quality, not interested in crypto. Follows markets and can be tempted by a hyped, riskier name. | **Push back** on a request inconsistent with his profile: flag the tension, explain the risks, never just agree. |

A comparison of two contrasting investors is suggested to show adaptability.

### Suggested building blocks (optional)

- **Explainability agent (or mechanism):** summarizes what supports a result, cites the data used, states assumptions, flags uncertainty.
- **Governance agent (or mechanism):** checks outputs against investor constraints and the simulation rules, flags conflicts or missing information, makes the checks visible.
- Suggested approach: formulate a useful question; define agent roles, data, tools, coordination and checkpoints; account for persona context; stress-test results (sensitivity to assumptions, data, scenarios); link every result to sources, assumptions, observable steps and limits.

### Deliverables

1. **Working prototype + code repo** showing one full use case with an accessible explanation (sources, assumptions, key drivers, limits). README must cover dependencies, data sources, configuration, setup/reproduction.
2. **Demo video**, about 5 minutes, end to end: problem, agent roles, data and tools, result, explanation given to the user.
3. **Technical documentation**: methods/models/tech and why; sources, assets, processing, assumptions; the explainability mechanism with an example tying a conclusion to data or execution traces; validation, limits, future work.
4. **One pager** (max one page): problem, agentic approach, originality, data sources, explainability, user benefits.

Deadlines, submission platform and infra requirements come in separate official logistics instructions.

### Judging grid (simplified, full grid is jury-only)

| Criterion | Weight |
| --- | --- |
| Quality, relevance and innovation of the solution | 20% |
| Agentic intelligence and explainability | 20% |
| Data analysis and processing | 20% |
| UX/UI | 10% |
| **AWS integration quality** | **15%** |
| Presentation, business value and marketing | 15% |

AWS integration is 15% of the grade: prefer AWS services (e.g. Bedrock for agents/LLMs, AWS hosting) when choosing the stack. A usable UI and a convincing demo matter more than complexity or past asset performance.

### Hard constraints (responsible framing)

- Simulation only: no real transactions, and the tool must not present itself as personalized financial advice.
- Clearly separate facts, assumptions and fictional scenarios; surface important uncertainties understandably.
- Explanations must be concise, verifiable and faithful to sources and observable actions: never invent justifications, do not expose detailed internal model reasoning.
- Do not predict future returns from past performance. Historical data describes assets (returns, volatility over an explicit period); volatility is one risk indicator among others (horizon, diversification, preferences matter too). Never map a profile to an asset automatically.
- Data rules: traceability (source, date, currency, processing), temporal consistency (observation date vs publication date, no look-ahead), comparability (dividends, splits, selection bias, missing data, CAD/USD), respect licenses, no real client accounts or confidential banking data (profiles and portfolios can be fully fictional).
- The starter dataset is optional; no asset or asset class is mandatory. Every added source must document relevance, origin, date, processing, limits and terms of use (see `data/external/sources.md`).

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
