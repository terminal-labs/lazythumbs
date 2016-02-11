# NOTE: These are the default paramaters used by lazythumbs for processing images with PIL.
#       We will try to get them from django settings, and if that fails we can use these
#       fallback values.

try:
    from django.conf import settings
except ImportError:
    ## NOTE: Use fallbacks
    settings = None

fallback_quality_factor = 60
fallback_optimize_flag = True
fallback_progressive_flag = True

DEFAULT_QUALITY_FACTOR = getattr(settings, 'LAZYTHUMBS_QUALITY_FACTOR', fallback_quality_factor)
DEFAULT_OPTIMIZE_FLAG = getattr(settings, 'LAZYTHUMBS_OPTIMIZE_FLAG', fallback_optimize_flag)
DEFAULT_PROGRESSIVE_FLAG = getattr(settings, 'LAZYTHUMBS_PROGRESSIVE_FLAG', fallback_progressive_flag)
