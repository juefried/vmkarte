import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = APP_DIR.parent.parent


def _resolve_shared_dir():
    """
    Resolves the single directory used for the map data.

    Priority:
    1. VMKARTE_SHARED_DIR environment variable
    2. <repo>/docker/webserver/www_data/shared when the web assets exist
    3. <app>/shared as a fallback (for example inside the Docker image)
    """
    override = os.environ.get('VMKARTE_SHARED_DIR', '').strip()
    if override:
        return Path(override).expanduser().resolve()

    repo_web_shared = REPO_ROOT / 'docker' / 'webserver' / 'www_data' / 'shared'
    if repo_web_shared.parent.is_dir():
        return repo_web_shared

    return APP_DIR / 'shared'


SHARED_DIR = _resolve_shared_dir()
CONFIG_PATH = APP_DIR / 'config.json'
CACHE_CONFIG_PATH = APP_DIR / 'cache_config.json'
CACHE_DIR = APP_DIR / 'cache'
MEMBERS_JSON_PATH = APP_DIR / 'members.json'
VMFORUM_MEMBERS_JSON_PATH = SHARED_DIR / 'vmforum_members.json'
