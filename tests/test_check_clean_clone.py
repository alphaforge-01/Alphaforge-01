"""Tests des contrôles de `scripts/check_clean_clone.py` (sans clone ni réseau)."""
from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_clean_clone.py"
spec = importlib.util.spec_from_file_location("check_clean_clone", SCRIPT)
ccc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = ccc  # requis par les dataclasses du script
spec.loader.exec_module(ccc)

EM_DASH = chr(0x2014)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_scan_detects_real_looking_aws_key(tmp_path):
    # Clé factice construite à l'exécution : le fichier de test ne contient aucune forme de clé (règle 6).
    fake_key = "AKIA" + "QWERTYUIOP" + "ASDFGH"
    leaked = _write(tmp_path / "src" / "config.py", f"KEY = '{fake_key}'\n")
    assert ccc.scan_text([leaked])["secrets"] == [leaked.as_posix()]


def test_scan_ignores_rule_text_and_keys_built_at_runtime(tmp_path):
    """Le texte de la règle 6 et une clé assemblée à l'exécution ne sont pas des clés écrites."""
    rule = _write(tmp_path / "CLAUDE.md", "never put access key IDs `AKIA...`/`ASIA...` in the repo\n")
    built = _write(tmp_path / "tests" / "t.py", 'key = "AKIA" + "QWERTYUIOP" + "ASDFGH"\n')
    assert ccc.scan_text([rule, built])["secrets"] == []


def test_scan_detects_em_dash_and_emoji(tmp_path):
    dash = _write(tmp_path / "docs" / "a.md", f"texte {EM_DASH} suite\n")
    emoji = _write(tmp_path / "docs" / "b.md", "bravo " + chr(0x1F680) + "\n")
    clean = _write(tmp_path / "docs" / "c.md", "texte - suite, accents : é à ç\n")
    found = ccc.scan_text([dash, emoji, clean])
    assert found["em_dash"] == [dash.as_posix()]
    assert found["emoji"] == [emoji.as_posix()]


def test_scan_flags_tracked_env_file(tmp_path):
    env = _write(tmp_path / ".env", "AWS_REGION=us-east-1\n")
    assert ccc.scan_text([env])["env"] == [str(env)]


def test_scan_skips_binary_files(tmp_path):
    binary = tmp_path / "image.png"
    binary.write_bytes(bytes(range(256)))
    assert ccc.scan_text([binary]) == {"secrets": [], "em_dash": [], "emoji": [], "env": []}


def test_root_violations(tmp_path):
    files = [tmp_path / "README.md", tmp_path / "notes.txt", tmp_path / "src" / "x.py", tmp_path / ".env.example"]
    assert ccc.root_violations(tmp_path, files) == ["notes.txt"]


@pytest.mark.parametrize("output,expected", [
    ("....\n2273 passed in 33.1s\n", 2273),
    ("1 failed, 2272 passed in 30s", 2272),
    ("no tests ran", None),
])
def test_passed_count(output, expected):
    assert ccc.passed_count(output) == expected


def test_venv_python_prefers_windows_layout(tmp_path):
    windows = _write(tmp_path / "Scripts" / "python.exe", "")
    assert ccc.venv_python(tmp_path) == windows
    assert ccc.venv_python(tmp_path / "other") == tmp_path / "other" / "bin" / "python"


def test_repository_root_is_compliant():
    """Le dépôt local respecte déjà la règle 5 (mêmes fichiers que le clone)."""
    root = SCRIPT.parents[1]
    if not (root / ".git").exists() or shutil.which("git") is None:
        pytest.skip("dépôt Git ou commande git indisponible (archive)")
    files = ccc.tracked_files(root)
    assert files, "git ls-files doit lister des fichiers"
    assert ccc.root_violations(root, files) == []


# ---------- corrections de la relecture ----------


def test_same_text_ignores_line_endings(tmp_path):
    lf = tmp_path / "a.md"
    crlf = tmp_path / "b.md"
    lf.write_bytes(b"ligne 1\nligne 2\n")
    crlf.write_bytes(b"ligne 1\r\nligne 2\r\n")
    assert ccc.same_text(lf, crlf)
    other = tmp_path / "c.md"
    other.write_bytes(b"ligne 1\nautre\n")
    assert not ccc.same_text(lf, other)


@pytest.mark.parametrize("name,expected", [
    (".env", True), (".env.local", True), (".env.production", True), (".env.example", False), ("env.py", False),
])
def test_is_env_file(name, expected):
    assert ccc.is_env_file(name) is expected


@pytest.mark.parametrize("text,expected", [("a\nb\n\n", "b"), ("", ""), ("   \n", "")])
def test_last_line(text, expected):
    assert ccc.last_line(text) == expected


def test_remove_tree_handles_read_only_files(tmp_path):
    import os
    import stat

    folder = tmp_path / "clone" / ".git" / "objects"
    locked = _write(folder / "pack.idx", "x")
    os.chmod(locked, stat.S_IREAD)
    assert ccc.remove_tree(tmp_path / "clone")


def test_secret_patterns_cover_env_and_yaml_styles(tmp_path):
    """Formes `AWS_SECRET_ACCESS_KEY=...` et `aws_secret_access_key: ...`, valeurs assemblées à l'exécution."""
    value = "A" * 20 + "b" * 20
    env_style = _write(tmp_path / "a.example", "AWS_SECRET_ACCESS_KEY=" + value + "\n")
    yaml_style = _write(tmp_path / "b.yaml", "aws_secret_access_key: " + value + "\n")
    empty = _write(tmp_path / ".env.example", "AWS_SECRET_ACCESS_KEY=\n")
    found = ccc.scan_text([env_style, yaml_style, empty])["secrets"]
    assert found == sorted([env_style.as_posix(), yaml_style.as_posix()])


def test_emoji_range_includes_star_symbols(tmp_path):
    star = _write(tmp_path / "a.md", "note " + chr(0x2B50) + "\n")
    arrow = _write(tmp_path / "b.md", "a " + chr(0x2192) + " b\n")
    assert ccc.scan_text([star, arrow])["emoji"] == [star.as_posix()]
