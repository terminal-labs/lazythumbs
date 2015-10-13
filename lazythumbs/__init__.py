__version__ = '0.4.4'

try:
    from django.conf import settings
    has_settings = True
except ImportError:
    has_settings = False

DEFAULT_QUALITY_FACTOR = settings.DEFAULT_QUALITY_FACTOR if has_settings else 80
DEFAULT_OPTIMIZE_FLAG = settings.DEFAULT_OPTIMIZE_FLAG if has_settings else True
DEFAULT_PROGRESSIVE_FLAG = settings.DEFAULT_PROGRESSIVE_FLAG if has_settings else True




