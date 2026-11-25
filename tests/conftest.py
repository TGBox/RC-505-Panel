import os
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def full_backup() -> Path:
    """Echtes ROLAND-Backup für die vollständigen Tests, z. B.
    $env:RC505_BACKUP = "D:\\RC 505 mk2 - Backup\\ROLAND"
    """
    p = os.environ.get("RC505_BACKUP")
    if not p or not (Path(p) / "DATA").is_dir():
        pytest.skip("RC505_BACKUP nicht gesetzt – vollständiger Backup-Test übersprungen")
    return Path(p)
