"""One owner for persistent paths; legacy P1/P2 files remain readable in place."""

import os
from pathlib import Path
import platform


def default_root():
    override = os.environ.get("MATH_GRADER_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if platform.system() == "Darwin":
        return Path.home() / "Library" / "Application Support" / "MathGrader"
    if platform.system() == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "MathGrader"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "math-grader"


class RuntimePaths:
    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.data = self.root / "data"
        self.originals = self.root / "images" / "originals"
        self.processed = self.root / "images" / "processed"
        self.models = self.root / "models"
        self.cache = self.root / "cache"
        self.logs = self.root / "logs"
        self.config = self.root / "config"
        self.legacy_pages = self.root / "pages"
        self.legacy_database = self.root / "math-grader.sqlite3"
        self.database = self.legacy_database if self.legacy_database.is_file() else self.data / "math-grader.sqlite3"

    def ensure(self):
        for path in (self.data, self.originals, self.processed, self.models,
                     self.cache, self.logs, self.config):
            path.mkdir(parents=True, exist_ok=True)
        return self

    def describe(self):
        return {name: str(getattr(self, name)) for name in
                ("root", "data", "database", "originals", "processed", "models", "cache", "logs", "config")}
