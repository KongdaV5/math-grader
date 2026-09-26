from contextlib import contextmanager
from pathlib import Path
import sqlite3


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.migrations_dir = Path(__file__).with_name("migrations")
        self.migrate()

    def connect(self):
        connection = sqlite3.connect(str(self.path), timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        return connection

    @contextmanager
    def connection(self):
        connection = self.connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self):
        connection = self.connect()
        try:
            current = connection.execute("PRAGMA user_version").fetchone()[0]
            migrations = sorted(self.migrations_dir.glob("[0-9]*_*.sql"))
            for migration in migrations:
                version = int(migration.name.split("_", 1)[0])
                if version <= current:
                    continue
                sql = migration.read_text(encoding="utf-8")
                try:
                    connection.executescript(
                        "BEGIN IMMEDIATE;\n" + sql + "\nPRAGMA user_version = {};\nCOMMIT;".format(version)
                    )
                except Exception:
                    connection.rollback()
                    raise
                current = version
        finally:
            connection.close()
