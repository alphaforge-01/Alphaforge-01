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
7. Data sources: only public or fictional data (required by the challenge). No real client accounts, no confidential banking information, no personal data of real people, ever: investor profiles, portfolios and capital amounts are fictional (the three personas or invented ones), and test fixtures/examples are invented too. Respect each public source's terms of use: before adding a source, check its terms (access, API limits, storage, redistribution) and record them in `data/external/sources.md`; if a source forbids redistribution, do not commit its raw files (git-ignore them and commit the download script instead); never scrape a site whose terms forbid it. If unsure whether data is allowed, ask the user before using it.
8. Simulation only: the prototype never executes real transactions and never presents itself as personalized financial advice. No tool, agent or integration may connect to a brokerage account or trading API (no order placement, no account linking, not even in "paper" mode against a real broker). Portfolios and allocations are fictional and labeled as such. User-facing outputs carry a short disclaimer (simulation, educational, not personalized advice) and separate facts, assumptions and fictional scenarios. When agents run on Amazon Bedrock, attach a Bedrock Guardrail to enforce this (e.g. a denied topic for personalized investment advice and trade execution requests, plus contextual grounding checks so answers stay faithful to the provided data), and surface guardrail interventions in the explanation trace.
9. Model routing: the main session runs on Sonnet at medium effort (`.claude/settings.json`) and does the regular building. Each subagent sets its model and reasoning effort in its frontmatter (`model:`, `effort:`), sized to the task so tokens go where they matter. Delegate to the project subagents in `.claude/agents/` without waiting to be asked, whenever a task matches:

| Task | Subagent | Model | Effort |
| --- | --- | --- | --- |
| Planning a feature or architecture | `planner` | Fable | high |
| Building a feature | main session | Sonnet | medium |
| UI, UX and frontend | `frontend-dev` | Sonnet | medium |
| AWS, Bedrock, Guardrails, IAM, credentials | `aws-integration` | Opus | xhigh |
| Codebase search, data lookups, renames, boilerplate | `explorer` | Haiku | low |
| Writing and running tests | `test-writer` | Sonnet | low |
| Hard bugs, or a first fix that failed | `debugger` | Opus | max |
| Security and compliance audit (rules 6 to 8) | `security-auditor` | Fable | xhigh |
| Code review before committing a feature | `code-reviewer` | Opus | high |

Run `planner` before any non-trivial feature, `code-reviewer` before committing a feature, and `security-auditor` before pushes touching AWS or data sources. Skip delegation for trivial tasks where it costs more than it saves. Relay subagent results to the user, since they do not see them.
10. Branches: never commit directly to `main`; it only receives merged pull requests. Start every piece of work on its own branch created from an up-to-date `main` (`git switch main && git pull && git switch -c <branch>`). Branch names reuse the commit types: `<type>/<short-description>` in English kebab-case, e.g. `feat/profile-builder`, `fix/fx-conversion`, `docs/use-case-decision`, `data/esg-evidence`, `chore/branch-workflow`. One branch per topic; keep it short-lived. Push with `git push -u origin <branch>` and merge into `main` through a GitHub pull request (title follows rule 3, description in French, no AI attribution per rule 2). Never force-push `main`; never rewrite history on a branch others use. If you find yourself on `main` with uncommitted work, create the branch before committing.
11. Guardrail enforcement: if a proposal, whether from the user, a teammate, a subagent or Claude itself, would go against any rule in this file (rules 1 to 10 and the hard constraints), Claude must not implement it. Claude says so explicitly and up front, names the rule that is violated, explains why in a sentence or two, and proposes the closest compliant alternative. This holds even if the request is phrased as a quick test, an example or a temporary shortcut. Only the user can change a rule, by editing this file; Claude never works around one silently.

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

## Exigences du projet et décisions

- Le prototype final doit intégrer AWS de façon réelle et démontrable dans sa chaîne de bout en bout. Cette intégration est une condition d'admissibilité, pas une raison d'ajouter des services sans utilité pour le cas d'usage.
- Aucun concept de produit, nombre d'agents ou architecture infonuagique n'est considéré comme choisi avant une décision explicite de l'équipe. Streamlit, Bedrock, Strands, AgentCore, SageMaker, S3, Lambda, Athena, Glue et Quick sont des options présentées par l'atelier, pas des instructions de déploiement.
- Rester dans le cadre d'une simulation éducative: aucune transaction réelle, connexion à un courtier, donnée bancaire ou client confidentielle, ni conseil financier personnalisé. Ne jamais fournir à un agent un outil de passage d'ordres.
- Calculer rendements, volatilité, perte maximale, corrélations et ratios avec du code déterministe testé. Un modèle de langage peut expliquer les résultats sourcés, mais ne doit ni inventer ni remplacer les calculs.
- Relier chaque résultat à des sources datées, transformations, hypothèses, résultats d'outils observables, incertitudes et limites. Ne pas exposer le raisonnement interne privé du modèle. Le README du projet doit expliquer les dépendances, sources, paramètres et étapes de reproduction.

## Environnement et opérations AWS

### Accès au compte

- L'équipe partage un seul compte Workshop Studio temporaire. Utiliser `us-east-1`, coordonner la création de ressources et considérer les quotas comme partagés.
- L'AWS CLI locale est déjà installée. Ne pas la réinstaller et ne pas créer de clé IAM permanente. S'authentifier avec CloudShell, déjà authentifié, ou avec l'ensemble complet d'identifiants temporaires de Workshop Studio: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` et `AWS_SESSION_TOKEN`.
- Placer les identifiants temporaires uniquement dans un terminal dédié, avec `AWS_REGION=us-east-1`. Exécuter la CLI et les processus SDK depuis ce même environnement. Ne pas utiliser `aws login` pour le compte de l'atelier, car il pourrait sélectionner un autre compte.
- Avant toute opération AWS, exécuter `aws sts get-caller-identity` et `aws configure list`, puis vérifier le compte et la région. En cas de `ExpiredToken`, `ExpiredTokenException` ou `InvalidClientTokenId`, récupérer un nouvel ensemble des trois valeurs temporaires.
- Ne pas créer, modifier, exposer ou supprimer une ressource simplement parce qu'un exemple de l'atelier le fait. Ne modifier AWS que pour une implémentation choisie par l'équipe et une tâche demandée par l'utilisateur.

### Persistance et secrets

- Considérer le compte AWS, le stockage CloudShell, les espaces SageMaker, les URL hébergées et le dossier Kiro partagé `/workshop` comme jetables. Garder le code, les prompts, la configuration et les artefacts reproductibles autorisés dans le dépôt. Une copie présente uniquement dans AWS ne doit jamais être la source de vérité.
- Ne jamais placer d'identifiants AWS, clés API, contenu de `.env` ou URL Kiro contenant un jeton dans le code, Git, les prompts d'un assistant, les journaux, les captures ou la documentation. Si un secret est exposé, cesser de l'utiliser et avertir un mentor ou un organisateur.
- Utiliser uniquement des données publiques ou fictives. Avant de téléverser des CSV financiers ou rapports publics dans le compte de l'atelier, confirmer avec un mentor que ces documents sont permis. Respecter les licences; si la redistribution est interdite, versionner le code de récupération et la provenance plutôt que le jeu complet. 
- Pour la remise, les identifiants temporaires de l'atelier peuvent être saisis dans les secrets de l'application Streamlit du projet, jamais dans le dépôt. Les secrets et l'application sont supprimés après la correction du jury.

### Sécurité par défaut

- Appliquer le moindre privilège à chaque rôle IAM. Distinguer le rôle de console du rôle d'exécution d'un notebook ou d'une application. Ne pas attacher une politique large comme `AmazonBedrockFullAccess` si des permissions d'inférence suffisent.
- Garder les quatre options S3 Block Public Access activées. Ne créer aucun bucket public ni ressource EC2, RDS ou EMR exposée publiquement.
- Préférer l'authentification IAM pour les URL Lambda. Utiliser `auth-type NONE` seulement si une démonstration publique approuvée l'exige, puis supprimer l'URL lorsqu'elle ne sert plus.
- Pour AgentCore Gateway, définir explicitement `--authorizer-type AWS_IAM`. Lier les serveurs MCP locaux à `127.0.0.1`. Comme `agentcore dev` écoute sur `0.0.0.0:8080`, l'arrêter dès qu'il n'est plus utilisé.

### Implémentation Bedrock et agents

- Interroger le compte pour connaître les modèles `ACTIVE` avant de choisir un identifiant. La disponibilité, les préfixes de profils d'inférence comme `us.` ou `global.`, l'acheminement régional et les sorties structurées varient selon le modèle et le compte. Ne pas coder autour d'un exemple non vérifié de l'atelier.
- Préférer l'API Converse de Bedrock pour les appels applicatifs. Le streaming nécessite un SDK. Parcourir tous les blocs de contenu contenant `text` au lieu de supposer que `content[0]` contient la réponse.
- Commencer avec un modèle peu coûteux, borner les tours et appels d'outils, puis gérer `ThrottlingException` avec un délai exponentiel. Conserver des traces utiles sans secrets, car les quotas sont partagés et les échecs doivent rester explicables.
- Donner aux outils des schémas précis et documenter leurs erreurs, sources, dates et devises. Avec Bedrock Guardrails, tester les requêtes permises et refusées. Les garde-fous complètent les contrôles applicatifs, mais ne prouvent pas l'exactitude factuelle.
- Pour le RAG, valider les passages retrouvés et leurs dates de publication, puis resynchroniser la base de connaissances après tout changement de source. La recherche fournit des preuves, elle ne calcule pas les métriques financières. Ne jamais introduire une publication future dans un scénario historique antérieur.
- Choisir le plus petit ensemble de services adapté au cas d'usage. Pour quelques mégaoctets de CSV, `pandas` local peut être plus approprié que Glue ou Athena. Utiliser S3, SageMaker, Lambda, AgentCore ou un autre service géré seulement si son rôle est concret et démontrable.

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
