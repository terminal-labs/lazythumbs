__version__ = '0.4.4'

import logging
logger = logging.getLogger('lazythumbs')


# NOTE: These are the default paramaters used by lazythumbs for processing images with PIL. 
#       We will try to get them from django settings, and if that fails we can use these
#       fallback values.

fallback_quality_factor = 80
fallback_optimize_flag = True
fallback_progressive_flag = True

try:
    from django.conf import settings

    try:
        DEFAULT_QUALITY_FACTOR = settings.DEFAULT_QUALITY_FACTOR
    except AttributeError:
        logger.debug("Failed to retrieve DEFAULT_QUALITY_FACTOR from django settings, it may not be set")

    try:
        DEFAULT_OPTIMIZE_FLAG = settings.DEFAULT_OPTIMIZE_FLAG
    except AttributeError:
        logger.debug("Failed to retrieve DEFAULT_OPTIMIZE_FLAG from django settings, it may not be set")

    try:
        DEFAULT_PROGRESSIVE_FLAG = settings.DEFAULT_PROGRESSIVE_FLAG
    except AttributeError:
        logger.debug("Failed to retrieve DEFAULT_PROGRESSIVE_FLAG from django settings, it may not be set")

except ImportError:
    logger.debug("Failed to import django settings")

finally:
    DEFAULT_QUALITY_FACTOR = DEFAULT_QUALITY_FACTOR if 'DEFAULT_QUALITY_FACTOR' in locals() else fallback_quality_factor
    DEFAULT_OPTIMIZE_FLAG = DEFAULT_OPTIMIZE_FLAG if 'DEFAULT_OPTIMIZE_FLAG' in locals() else fallback_optimize_flag
    DEFAULT_PROGRESSIVE_FLAG = DEFAULT_PROGRESSIVE_FLAG if 'DEFAULT_PROGRESSIVE_FLAG' in locals() else fallback_progressive_flag

