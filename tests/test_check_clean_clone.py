"""Tests des contrôles de `scripts/check_clean_clone.py` (sans clone ni réseau)."""
from __future__ import annotations

import importlib.util
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


def test_scan_ignores_rule_text_and_fake_test_keys(tmp_path):
    rule = _write(tmp_path / "CLAUDE.md", "never put access key IDs `AKIA...`/`ASIA...` in the repo\n")
    fake = _write(tmp_path / "tests" / "t.py", "key = 'AKIAABCDEFGHIJKLMNOP'\n")
    assert ccc.scan_text([rule, fake])["secrets"] == []


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
    files = ccc.tracked_files(root)
    assert files, "git ls-files doit lister des fichiers"
    assert ccc.root_violations(root, files) == []
