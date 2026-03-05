from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)
from .bot import TelegramBot
from .handlers import setup_handlers
__all__ = ['TelegramBot', 'setup_handlers']
