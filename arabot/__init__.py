from os import getenv as _getenv

from dotenv import load_dotenv as _load_dotenv

from .core import Ara

__version__ = "7.2.0"

_load_dotenv()
TESTING = bool(_getenv("testing"))
