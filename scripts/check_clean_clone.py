"""Vérification depuis un clone propre : refaire ce que fera le jury, à partir de GitHub seulement.

Le script clone la branche demandée (par défaut `main` du dépôt `origin`) dans un dossier
temporaire vide, puis suit le README :

1. contrôles du dépôt cloné : fichiers à la racine (règle 5), aucun secret apparent
   (règle 6), aucun tiret cadratin ni emoji dans les fichiers texte (règle 1), aucun `.env` ;
2. environnement Python (voir ci-dessous) et preuve que `requirements.txt` suffit ;
3. dépendances **réellement chargées** : pandas, numpy, pyarrow, streamlit, boto3, pytest
   s'importent, et pandas a bien chargé PyArrow (pandas avale l'erreur sinon) ; en cas
   d'échec, les étapes suivantes ne sont pas exécutées et ne comptent jamais comme réussies ;
4. suite de tests complète (`pytest -q -W error`), avec le nombre exact de tests ;
5. `scripts/run_scenarios.py` (hors ligne) ;
6. `scripts/run_sensitivity.py` : le rapport régénéré doit être identique au rapport versionné ;
7. interface jouée sans navigateur (`streamlit.testing`) : accueil, profil de Robert,
   demande TSLA 25 %, statut « Conflit » affiché, aucune exception.

Environnement Python, deux modes :

- par défaut, **réutilisation** de l'environnement qui lance le script (le `.venv` du projet).
  Sous Windows 11 avec Smart App Control, chaque nouvelle copie d'une DLL non signée (par
  exemple celle de PyArrow, extraite par pip) est bloquée : un environnement neuf à chaque
  passage ferait échouer le chargement à chaque fois. On réutilise donc des fichiers que
  Windows autorise déjà, sans rien désactiver ni contourner. L'isolation est vérifiée :
  `pip install --dry-run -r requirements.txt` ne doit rien avoir à installer ; chaque
  bibliothèque importée par le clone doit venir de `requirements.txt` ou de ses dépendances
  (un paquet installé à la main serait signalé) ; `alphaforge` ne doit pas être installé dans
  l'environnement, il est lu dans le clone ;
- `--fresh-env` : environnement neuf, installation de `requirements.txt` seul (machine sans
  Smart App Control : Linux, autre poste).

Rien n'est envoyé à AWS : tout tourne en mode hors ligne. Le dépôt local n'est pas modifié.
Le clone utilise l'authentification Git déjà configurée sur le poste (dépôt privé).

Usage (depuis la racine) ::

    .venv/Scripts/python scripts/check_clean_clone.py
    .venv/Scripts/python scripts/check_clean_clone.py --branch main --keep
    .venv/Scripts/python scripts/check_clean_clone.py --fresh-env --python C:/chemin/vers/python3.11.exe

Codes de sortie : 0 tout est vert, 1 au moins une vérification en échec (dont une dépendance
bloquée), 2 clone ou installation impossible.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

EXIT_OK, EXIT_FAILURES, EXIT_SETUP = 0, 1, 2
# Racine autorisée par la règle 5 de CLAUDE.md (plus les dossiers de premier niveau).
ALLOWED_ROOT_FILES = frozenset({"README.md", ".gitignore", "CLAUDE.md", "requirements.txt", "pyproject.toml",
                                ".env.example"})
TEXT_SUFFIXES = frozenset({".py", ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".csv", ".sh", ".ipynb",
                           ".cfg", ".ini", ".example"})
# Formes de secrets AWS ; les mentions de la règle elle-même (`AKIA...`) ne sont pas des clés.
SECRET_PATTERNS = (
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"aws_secret_access_key['\"]?\s*[=:]\s*['\"]?[A-Za-z0-9/+]{40}", re.IGNORECASE),
    re.compile(r"aws_session_token['\"]?\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{100,}", re.IGNORECASE),
)
EM_DASH = "\u2014"
# Pictogrammes et emoji (symboles divers, dingbats, \u00E9toiles, plans emoji). Les symboles comme
# U+2713 ou U+2605 comptent aussi : la r\u00E8gle 1 demande une ponctuation ASCII simple.
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF]")
SUMMARY_LINE = re.compile(r"(\d+) passed")

# Bibliothèques compilées ou centrales à charger réellement avant de croire les tests.
REQUIRED_IMPORTS = ("numpy", "pandas", "pyarrow", "streamlit", "boto3", "pytest")
# Import facultatif documenté : reconstruction volontaire des données seulement (README).
OPTIONAL_IMPORTS = {"yfinance": "scripts/build_dataset.py"}

DEPENDENCY_PROBE = r'''
import importlib, sys
problems = []
for name in sys.argv[1:]:
    try:
        importlib.import_module(name)
    except Exception as error:  # ImportError, OSError : DLL refusée, paquet absent
        problems.append(f"{name} : {type(error).__name__} : {error}")
import pandas  # pandas attrape l'échec de PyArrow et continue sans lui : on le vérifie à part
if "pyarrow" not in sys.modules:
    problems.append("pandas fonctionne sans PyArrow (import refusé ou absent)")
print("\n".join(problems) if problems else "toutes les dépendances sont chargées")
sys.exit(1 if problems else 0)
'''

IMPORT_AUDIT = r'''
import ast, json, pathlib, re, sys
from importlib import metadata
root = pathlib.Path.cwd()
folders = ["src", "app", "scripts", "tests"]
optional = json.loads(sys.argv[1])
norm = lambda s: re.sub(r"[-_.]+", "-", s).lower()
local = {"alphaforge", "app", "__future__"}
for folder in folders:
    base = root / folder
    if base.exists():
        local |= {p.stem if p.suffix == ".py" else p.name for p in base.iterdir()}
imports = {}
for folder in folders:
    for path in (root / folder).rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                imports.setdefault(name.split(".")[0], set()).add(path.relative_to(root).as_posix())
third = {n: files for n, files in imports.items() if n not in sys.stdlib_module_names and n not in local}
requirements = [re.split(r"[<>=!~;\[ ]", line.strip())[0] for line in open("requirements.txt", encoding="utf-8")
                if line.strip() and not line.lstrip().startswith("#")]
closure, stack = set(), [norm(r) for r in requirements]
while stack:
    name = stack.pop()
    if name in closure:
        continue
    closure.add(name)
    try:
        requires = metadata.distribution(name).requires or []
    except metadata.PackageNotFoundError:
        continue
    stack += [norm(re.split(r"[<>=!~;\[ (]", r.strip())[0]) for r in requires if "extra ==" not in r]
providers = metadata.packages_distributions()
problems = []
for name, files in sorted(third.items()):
    if name in optional and files <= {optional[name]}:
        continue
    dists = [norm(d) for d in providers.get(name, [])]
    if not dists:
        problems.append(f"{name} : aucun paquet installé ({', '.join(sorted(files))[:120]})")
    elif not any(d in closure for d in dists):
        problems.append(f"{name} : paquet {', '.join(dists)} absent de requirements.txt ({', '.join(sorted(files))[:120]})")
print("\n".join(problems) if problems else f"{len(third)} bibliothèques importées, toutes couvertes par requirements.txt")
sys.exit(1 if problems else 0)
'''

ALPHAFORGE_NOT_INSTALLED = r'''
import importlib.util, sys
spec = importlib.util.find_spec("alphaforge")
print("alphaforge lu dans le clone" if spec is None else f"alphaforge installé dans l'environnement : {spec.origin}")
sys.exit(0 if spec is None else 1)
'''

APP_SMOKE = r'''
import pathlib, sys
from streamlit.testing.v1 import AppTest
root = pathlib.Path.cwd()
at = AppTest.from_file(str(root / "app" / "streamlit_app.py"), default_timeout=180).run()
assert not at.exception, [e.value for e in at.exception]
at.button(key="choose_profile_robert").click().run()
at.switch_page("views/simulation_page.py").run()
at.button(key="idea_preset_TSLA_25").click().run()
at.button(key="idea_submit").click().run()
assert not at.exception, [e.value for e in at.exception]
texts = [m.value for m in at.markdown] + [e.value for e in (*at.error, *at.warning, *at.info, *at.success)]
assert any("Conflit" in t for t in texts), "statut Conflit absent pour Robert TSLA 25 %"
print("interface : accueil, profil Robert, TSLA 25 %, Conflit affiché, aucune exception")
'''


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    seconds: float = 0.0


@dataclass
class Report:
    checks: list = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str = "", seconds: float = 0.0) -> bool:
        self.checks.append(Check(name, ok, detail, seconds))
        status = "OK    " if ok else "ÉCHEC "
        print(f"{status} {name}" + (f" : {detail}" if detail else "") + (f" ({seconds:.0f} s)" if seconds else ""))
        return ok

    @property
    def all_ok(self) -> bool:
        return all(check.ok for check in self.checks)


CLONE_TIMEOUT = 300


def run(command: list, cwd: Path, timeout: int = 1800) -> tuple[int, str, float]:
    """Exécute une commande ; rend (code, sortie combinée, durée).

    `PYTHONIOENCODING` : accents lisibles. `GIT_TERMINAL_PROMPT=0` : sans identifiants, git
    échoue au lieu d'attendre un mot de passe.
    """
    start = time.perf_counter()
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "GIT_TERMINAL_PROMPT": "0"}
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=timeout, env=env)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or ""), time.perf_counter() - start


def last_line(text: str, limit: int = 300) -> str:
    """Dernière ligne non vide d'une sortie (chaîne vide si aucune)."""
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:limit] if lines else ""


def same_text(first: Path, second: Path) -> bool:
    """Contenu identique aux fins de ligne près (LF versionné, CRLF possible sous Windows)."""
    return first.read_bytes().replace(b"\r\n", b"\n") == second.read_bytes().replace(b"\r\n", b"\n")


def is_env_file(name: str) -> bool:
    """`.env` et ses variantes (`.env.local`...), sauf le modèle `.env.example`."""
    return name == ".env" or (name.startswith(".env.") and name != ".env.example")


def remove_tree(path: Path) -> bool:
    """Supprime un dossier, y compris les fichiers en lecture seule de `.git` sous Windows."""
    def make_writable_and_retry(function, target, *_):
        os.chmod(target, stat.S_IWRITE)
        function(target)

    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=make_writable_and_retry)
    else:  # Python 3.11
        shutil.rmtree(path, onerror=make_writable_and_retry)
    return not path.exists()


def venv_python(venv: Path) -> Path:
    windows = venv / "Scripts" / "python.exe"
    return windows if windows.exists() else venv / "bin" / "python"


def tracked_files(clone: Path) -> list[Path]:
    code, out, _ = run(["git", "ls-files"], clone)
    return [clone / line for line in out.splitlines() if line.strip()] if code == 0 else []


def root_violations(clone: Path, files: list[Path]) -> list[str]:
    """Fichiers suivis à la racine qui ne sont pas autorisés par la règle 5."""
    return sorted(p.name for p in files if p.parent == clone and p.name not in ALLOWED_ROOT_FILES)


def scan_text(files: list[Path]) -> dict[str, list[str]]:
    """Secrets apparents, tirets cadratins et emoji dans les fichiers texte suivis."""
    found = {"secrets": [], "em_dash": [], "emoji": [], "env": []}
    for path in files:
        if is_env_file(path.name):
            found["env"].append(str(path))
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".env.example":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        name = path.as_posix()
        if any(pattern.search(text) for pattern in SECRET_PATTERNS):
            found["secrets"].append(name)
        if EM_DASH in text:
            found["em_dash"].append(name)
        if EMOJI.search(text):
            found["emoji"].append(name)
    return {key: sorted(set(value)) for key, value in found.items()}


def passed_count(pytest_output: str) -> int | None:
    """Nombre de tests réussis lu dans le résumé de pytest."""
    matches = SUMMARY_LINE.findall(pytest_output)
    return int(matches[-1]) if matches else None


def check_repository(report: Report, clone: Path) -> None:
    files = tracked_files(clone)
    report.add("fichiers suivis par Git", bool(files), f"{len(files)} fichiers")
    bad_root = root_violations(clone, files)
    report.add("racine conforme à la règle 5", not bad_root, ", ".join(bad_root))
    scan = scan_text(files)
    report.add("aucun fichier .env suivi", not scan["env"], ", ".join(scan["env"]))
    report.add("aucun secret apparent", not scan["secrets"], ", ".join(scan["secrets"][:5]))
    report.add("aucun tiret cadratin", not scan["em_dash"], ", ".join(scan["em_dash"][:5]))
    report.add("aucun emoji", not scan["emoji"], ", ".join(scan["emoji"][:5]))


def prepare_fresh_environment(report: Report, interpreter: str, workdir: Path, clone: Path) -> Path | None:
    """Mode `--fresh-env` : environnement neuf et installation de `requirements.txt` seul."""
    venv = workdir / "venv"
    code, out, seconds = run([interpreter, "-m", "venv", str(venv)], workdir)
    if not report.add("environnement Python neuf", code == 0, last_line(out) if code else "", seconds):
        return None
    python = venv_python(venv)
    code, out, seconds = run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q",
                              "-r", "requirements.txt"], clone)
    if not report.add("installation de requirements.txt seulement", code == 0, last_line(out) if code else "",
                      seconds):
        return None
    return python


def nothing_to_install(pip_output: str) -> bool:
    """Vrai si `pip install --dry-run` n'a rien à installer."""
    return "Would install" not in pip_output


def verify_reused_environment(report: Report, python: Path, workdir: Path, clone: Path) -> None:
    """Mode par défaut : l'environnement réutilisé doit se comporter comme un environnement propre."""
    report.add("environnement réutilisé (fichiers déjà autorisés par Windows)", python.exists(), str(python))
    code, out, seconds = run([str(python), "-m", "pip", "install", "--dry-run", "--disable-pip-version-check",
                              "-r", "requirements.txt"], clone)
    satisfied = code == 0 and nothing_to_install(out)
    report.add("requirements.txt satisfait sans rien installer", satisfied,
               "" if satisfied else last_line(out), seconds)
    code, out, seconds = run([str(python), "-c", IMPORT_AUDIT, json.dumps(OPTIONAL_IMPORTS)], clone)
    report.add("imports du clone couverts par requirements.txt", code == 0,
               "; ".join(out.strip().splitlines())[:400], seconds)
    code, out, _ = run([str(python), "-c", ALPHAFORGE_NOT_INSTALLED], workdir)
    report.add("alphaforge lu dans le clone, pas dans l'environnement", code == 0, last_line(out))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vérification depuis un clone propre (mode hors ligne, sans AWS).")
    parser.add_argument("--repo", default=None, help="URL du dépôt (défaut : origin du dépôt local)")
    parser.add_argument("--branch", default="main", help="Branche à vérifier (défaut : main)")
    parser.add_argument("--fresh-env", action="store_true",
                        help="Créer un environnement neuf (machine sans Smart App Control)")
    parser.add_argument("--python", default=sys.executable,
                        help="Interpréteur réutilisé (défaut : celui qui lance le script) ou base de --fresh-env")
    parser.add_argument("--keep", action="store_true", help="Garder le dossier du clone à la fin")
    args = parser.parse_args(argv)
    try:  # accents lisibles dans la console Windows
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    repo = args.repo
    if repo is None:
        try:
            code, out, _ = run(["git", "remote", "get-url", "origin"], PROJECT_ROOT)
        except FileNotFoundError:
            print("git est introuvable : l'installer avant la vérification.")
            return EXIT_SETUP
        repo = out.strip() if code == 0 else None
    if not repo:
        print("Dépôt introuvable : passer --repo.")
        return EXIT_SETUP

    workdir = Path(tempfile.mkdtemp(prefix="alphaforge_clean_clone_"))
    clone = workdir / "repo"
    report = Report()
    print(f"Clone propre de la branche {args.branch} dans {clone}")
    try:
        code, out, seconds = run(["git", "clone", "--depth", "1", "--branch", args.branch, "--", repo, str(clone)],
                                 workdir, timeout=CLONE_TIMEOUT)
        if not report.add("clone depuis GitHub", code == 0, last_line(out) if code else "", seconds):
            return EXIT_SETUP
        code, out, _ = run(["git", "log", "--oneline", "-1"], clone)
        print(f"Commit vérifié : {out.strip()}")

        check_repository(report, clone)

        if args.fresh_env:
            python = prepare_fresh_environment(report, args.python, workdir, clone)
            if python is None:
                return EXIT_SETUP
        else:
            python = Path(args.python)
            verify_reused_environment(report, python, workdir, clone)
        code, out, _ = run([str(python), "--version"], workdir)
        print(f"Interpréteur : {out.strip()} ({python})")

        # Dépendances réellement chargées : sans elles, un test « réussi » ne prouve rien.
        code, out, seconds = run([str(python), "-c", DEPENDENCY_PROBE, *REQUIRED_IMPORTS], clone)
        loaded = report.add("dépendances réellement chargées", code == 0,
                            "; ".join(out.strip().splitlines())[:400], seconds)
        if not loaded:
            report.add("tests, scénarios, sensibilité et interface", False,
                       "non exécutés : une dépendance est bloquée ou absente, un résultat ne serait pas fiable")
            if "contrôle d" in out or "application control" in out.lower():
                print("Windows (Smart App Control) a bloqué une DLL de cet environnement. Relancer sans --fresh-env "
                      "pour réutiliser le .venv du projet, dont les fichiers sont déjà autorisés.")
            return EXIT_FAILURES

        code, out, seconds = run([str(python), "-m", "pytest", "-q", "-W", "error", "-p", "no:cacheprovider"], clone)
        count = passed_count(out)
        report.add("tests (pytest -q -W error)", code == 0,
                   f"{count} tests réussis" if code == 0 else last_line(out), seconds)

        code, out, seconds = run([str(python), "scripts/run_scenarios.py"], clone)
        report.add("scripts/run_scenarios.py (hors ligne)", code == 0, "" if code == 0 else out.strip()[-300:], seconds)

        regenerated = workdir / "sensitivity"
        code, out, seconds = run([str(python), "scripts/run_sensitivity.py", "--out-dir", str(regenerated)], clone)
        committed = clone / "outputs" / "reports" / "sensitivity.md"
        same = (code == 0 and committed.exists() and (regenerated / "sensitivity.md").exists()
                and same_text(committed, regenerated / "sensitivity.md"))
        report.add("rapport de sensibilité identique au rapport versionné", same,
                   "" if same else (out.strip()[-300:] if code else "contenu différent"), seconds)

        code, out, seconds = run([str(python), "-c", APP_SMOKE], clone)
        smoke_line = next((line for line in out.splitlines() if line.startswith("interface :")), "")
        report.add("interface sans navigateur", code == 0,
                   smoke_line.removeprefix("interface : ") if code == 0 else out.strip()[-300:], seconds)
    except subprocess.TimeoutExpired as error:
        report.add("délai dépassé", False, str(error.cmd)[:200])
    except FileNotFoundError as error:  # git absent ou --python invalide
        report.add("outil introuvable", False, str(error)[:200])
        return EXIT_SETUP
    finally:
        if args.keep:
            print(f"Dossier gardé : {workdir}")
        elif not remove_tree(workdir):
            print(f"Dossier temporaire non supprimé, à effacer à la main : {workdir}")

    failed = [check.name for check in report.checks if not check.ok]
    print()
    print("Bilan : " + ("tout est vert." if not failed else f"{len(failed)} échec(s) : {', '.join(failed)}"))
    return EXIT_OK if report.all_ok else EXIT_FAILURES


if __name__ == "__main__":
    raise SystemExit(main())
