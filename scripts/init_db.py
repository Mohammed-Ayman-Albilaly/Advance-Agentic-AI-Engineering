"""Initialize UniFlow AI application SQLite schema."""

from app.config import get_settings
from app.persistence import Database


def main() -> None:
    settings = get_settings()
    db = Database(settings.database_path)
    db.initialize()
    if not db.health_check():
        raise SystemExit("Database health check failed")
    print(f"Initialized application database: {settings.database_path}")


if __name__ == "__main__":
    main()
