from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv():
    env_path = BASE_DIR / '.env'
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


_load_dotenv()

APP_NAME = os.getenv('APP_NAME', 'ElectroStock')
DATA_DIR = Path(os.getenv('APP_DATA_DIR', '/app/data'))
DB_URL = os.getenv('APP_DB_URL', f'sqlite:///{DATA_DIR / "app.db"}')
SECRET_KEY = os.getenv('APP_SECRET_KEY', 'change-me')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '').strip()
OPENAI_COMPONENT_LOOKUP_MODEL = os.getenv('OPENAI_COMPONENT_LOOKUP_MODEL', 'gpt-4o-mini').strip() or 'gpt-4o-mini'
OPENAI_COMPONENT_LOOKUP_USE_WEB_SEARCH = _as_bool(os.getenv('OPENAI_COMPONENT_LOOKUP_USE_WEB_SEARCH'), True)
OPENAI_COMPONENT_LOOKUP_TIMEOUT = int(os.getenv('OPENAI_COMPONENT_LOOKUP_TIMEOUT', '45'))
OPENAI_RESPONSES_API_URL = os.getenv('OPENAI_RESPONSES_API_URL', 'https://api.openai.com/v1/responses').strip()
MAX_CATEGORY_DEPTH = 6
IMAGE_MAX_SIZE = (1200, 1200)
THUMBNAIL_MAX_SIZE = (320, 320)
IMAGE_QUALITY = 78
COMPONENT_IMAGES_DIR = DATA_DIR / 'images' / 'components'
THUMBNAIL_IMAGES_DIR = DATA_DIR / 'images' / 'thumbnails'
