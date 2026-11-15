"""Vérification depuis un clone propre : refaire ce que fera le jury, à partir de GitHub seulement.

Le script clone la branche demandée (par défaut `main` du dépôt `origin`) dans un dossier
temporaire vide, crée un environnement Python neuf, installe **uniquement**
`requirements.txt`, puis suit le README :

1. contrôles du dépôt cloné : fichiers à la racine (règle 5), aucun secret apparent
   (règle 6), aucun tiret cadratin ni emoji dans les fichiers texte (règle 1), aucun `.env` ;
2. installation des dépendances ;
3. suite de tests complète (`pytest -q -W error`), avec le nombre exact de tests ;
4. `scripts/run_scenarios.py` (hors ligne) ;
5. `scripts/run_sensitivity.py` : le rapport régénéré doit être identique, octet pour octet,
   à `outputs/reports/sensitivity.md` versionné (reproductibilité) ;
6. interface jouée sans navigateur (`streamlit.testing`) : accueil, profil de Robert,
   demande TSLA 25 %, statut « Conflit » affiché, aucune exception.

Rien n'est envoyé à AWS : tout tourne en mode hors ligne. Le dépôt local n'est pas modifié.
Le clone utilise l'authentification Git déjà configurée sur le poste (dépôt privé).

Usage (depuis la racine) ::

    .venv/Scripts/python scripts/check_clean_clone.py
    .venv/Scripts/python scripts/check_clean_clone.py --branch main --keep
    .venv/Scripts/python scripts/check_clean_clone.py --python C:/chemin/vers/python3.11.exe

Codes de sortie : 0 tout est vert, 1 au moins une vérification en échec, 2 clone ou
installation impossible.
"""
from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vérification depuis un clone propre (mode hors ligne, sans AWS).")
    parser.add_argument("--repo", default=None, help="URL du dépôt (défaut : origin du dépôt local)")
    parser.add_argument("--branch", default="main", help="Branche à vérifier (défaut : main)")
    parser.add_argument("--python", default=sys.executable, help="Interpréteur pour créer l'environnement neuf")
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

        venv = workdir / "venv"
        code, out, seconds = run([args.python, "-m", "venv", str(venv)], workdir)
        if not report.add("environnement Python neuf", code == 0, out.strip()[-200:] if code else "", seconds):
            return EXIT_SETUP
        python = venv_python(venv)
        code, out, _ = run([str(python), "--version"], workdir)
        print(f"Interpréteur : {out.strip()}")
        code, out, seconds = run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-q",
                                  "-r", "requirements.txt"], clone)
        if not report.add("installation de requirements.txt seulement", code == 0, out.strip()[-300:] if code else "",
                          seconds):
            return EXIT_SETUP

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
