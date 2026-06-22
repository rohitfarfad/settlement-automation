from pathlib import Path


def load_local_env(project_root: Path) -> None:
    """
    Loads .env for local development if python-dotenv is installed.

    In production, environment variables should usually be injected by the
    runtime environment instead of loaded from a file.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    env_path = project_root / ".env"

    if env_path.exists():
        load_dotenv(env_path)