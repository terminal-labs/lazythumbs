from cStringIO import StringIO
from hashlib import md5
import errno
import logging
import os
import re
import types

from django.conf import settings
from django.core.cache import cache
from django.core.files.storage import FileSystemStorage
from django.core.files.base import ContentFile
from django.core.exceptions import SuspiciousOperation
from django.http import HttpResponse
from django.views.generic.base import View
from PIL import Image

from lazythumbs.settings import DEFAULT_QUALITY_FACTOR, DEFAULT_OPTIMIZE_FLAG, DEFAULT_PROGRESSIVE_FLAG
from lazythumbs.util import geometry_parse, get_format

logger = logging.getLogger('lazythumbs')

MATTE_BACKGROUND_COLOR = getattr(settings, 'LAZYTHUMBS_MATTE_BACKGROUND_COLOR', (0, 0, 0))

DEFAULT_QUALITY_URL_PARAM = 'q{0}'.format(DEFAULT_QUALITY_FACTOR)

def action(fun):
    """
    Decorator used to denote an instance method as an action: a function
    that takes a path to an image, performs PIL on it, and returns raw image
    data.
    """
    fun.is_action = True
    return fun


class LazyThumbRenderer(View):
    """
    Perform requested image render operations and handle fs logic and caching
    of 404s. Maps a requested action (currently 'thumbnail' and 'resize' are
    supported) to a matching method named after the action prefixed with
    'action_'. Once the argument signatures are relaxed one can implement new
    image transformations simply by subclassing this view and adding "action_"
    methods that return raw image data as a string.
    """
    def __init__(self):
        self.fs = FileSystemStorage()
        self.allowed_actions = [a.__name__
            for a in (getattr(self, a, None) for a in dir(self))
            if type(a) == types.MethodType and getattr(a, 'is_action', False)
        ]


    def get(self, request, action, geometry, source_path, quality=DEFAULT_QUALITY_URL_PARAM):
        """
        Perform action routing and handle sanitizing url input. Handles caching the path to a rendered image to
        django.cache and saves the new image on the filesystem. 404s are cached to
        save time the next time the missing image is requested.

        :param request: HttpRequest
        :param action: some action, eg thumbnail or resize
        :param geometry: a string of either '\dx\d' or just '\d'
        :param source_path: the fs path to the image to be manipulated
        :param quality: a string of 'q\d'
        :returns: an HttpResponse with an image/{format} content_type
        """
        # sanitize quality param
        try:
            quality = int(quality.lstrip('q'))
        except (ValueError, AttributeError), e:
            logger.info('corrupted quality "%s" for action "%s"', quality, action)
            logger.info('Bad url quality parameter:\n%s', e)
            return self.four_oh_four()

        if not 0 < quality <= 100:
            logger.info('corrupted quality "%s" for action "%s"', quality, action)
            return self.four_oh_four()

        # reject naughty paths and actions
        if source_path.startswith('/'):
            logger.info("%s: blocked bad path", source_path)
            return self.four_oh_four()
        if re.match('\.\./', source_path):
            logger.info("%s: blocked bad path", source_path)
            return self.four_oh_four()
        if action not in self.allowed_actions:
            logger.info("%s: bad action requested: %s", source_path, action)
            return self.four_oh_four()

        try:
            width, height = geometry_parse(action, geometry, ValueError)
        except ValueError, e:
            logger.info('corrupted geometry "%s" for action "%s"', geometry, action)
            return self.four_oh_four()

        width = int(width) if width is not None else None
        height = int(height) if height is not None else None

        rendered_path = request.path[1:]

        cache_key = self.cache_key(source_path, action, width, height, quality)
        was_404 = cache.get(cache_key)

        if was_404 == 1:
            return self.four_oh_four()

        img_format = get_format(rendered_path)
        # TODO this tangled mess of try/except is hideous... but such is
        # filesystem io? No it can be cleaned up by splitting it out
        try:
            # does rendered file already exist?
            raw_data = self.fs.open(rendered_path).read()
        except IOError as e:
            if was_404 == 0:
                # then it *was* here last time. if was_404 had been None then
                # it makes sense for rendered image to not exist yet: we
                # probably haven't seen it, or it dropped out of cache.
                logger.info('rendered image previously on fs missing. regenerating')
            try:
                pil_img = getattr(self, action)(
                    width=width,
                    height=height,
                    img_path=source_path
                )
                # this code from sorl-thumbnail
                buf = StringIO()
                # TODO we need a better way of choosing options based on size and format
                params = {
                    'format': get_format(rendered_path),
                    'quality': quality,
                    'optimize': DEFAULT_OPTIMIZE_FLAG,
                    'progressive': DEFAULT_PROGRESSIVE_FLAG,
                }

                if params['format'] == "JPEG" and pil_img.mode == 'P':
                    # Cannot save mode 'P' image as JPEG without converting first
                    # (This can happen if we have a GIF file without an extension and don't scale it)
                    pil_img = pil_img.convert()

                try:
                    pil_img.save(buf, **params)
                except IOError as e:
                    logger.exception("pil_img.save(%r)", params)
                    # TODO reevaluate this except when we make options smarter
                    logger.info("Failed to create new image %s . Trying without options", rendered_path)
                    pil_img.save(buf, format=img_format)
                raw_data = buf.getvalue()
                buf.close()
                try:
                    self.fs.save(rendered_path, ContentFile(raw_data))
                except OSError as e:
                    if e.errno == errno.EEXIST:
                        # possible race condition, another WSGI worker wrote file or directory first
                        # try to read again
                        try:
                            raw_data = self.fs.open(rendered_path).read()
                        except Exception as e:
                            logger.exception("Unable to read image file, returning 404: %s", e)
                            return self.four_oh_four()
                    else:
                        logger.exception("Saving converted image: %s", e)
                        raise

            except (IOError, SuspiciousOperation, ValueError), e:
                # we've now failed to find a rendered path as well as the
                # original source path. this is a 404.
                logger.info('404: %s', e)
                cache.set(cache_key, 1, settings.LAZYTHUMBS_404_CACHE_TIMEOUT)
                return self.four_oh_four()

        cache.set(cache_key, 0, settings.LAZYTHUMBS_CACHE_TIMEOUT)

        return self.two_hundred(raw_data, img_format)

    @action
    def resize(self, *args, **kwargs):
        """
        Thumbnail and crop. Thumbnails along larger dimension and then center
        crops to meet desired dimension.

        :param width: desired width in pixels. required.
        :param height: desired height in pixels. required.
        :param img_path: a path to an image on the filesystem
        :param img: a PIL Image object
        :returns: a PIL Image object
        """
        return self._resize(*args, **kwargs)

    @action
    def mresize(self, *args, **kwargs):
        """
        Identical to `resize`, except we will allow matting on all sides of the
        image in order to return an image that is the requested size.

        :param width: desired width in pixels. required.
        :param height: desired height in pixels. required.
        :param img_path: a path to an image on the filesystem
        :param img: a PIL Image object
        :returns: a PIL Image object
        """
        return self._resize(*args, allow_undersized=True, **kwargs)

    def _resize(
        self, width, height, img_path=None, img=None, allow_undersized=False
    ):
        """
        Thumbnail and crop. Thumbnails along larger dimension and then center
        crops to meet desired dimension.

        :param width: desired width in pixels. required.
        :param height: desired height in pixels. required.
        :param img_path: a path to an image on the filesystem
        :param img: a PIL Image object
        :returns: a PIL Image object
        """
        if not (img or img_path):
            raise ValueError('unable to find img given args')
        img = img or self.get_pil_from_path(img_path)

        source_width = img.size[0]
        source_height = img.size[1]

        if (
            not allow_undersized
            and width >= source_width
            and height >= source_height
        ):
            return img

        img = self.thumbnail(
            width = width if source_width < source_height else None,
            height = height if source_height <= source_width else None,
            img = img
        )

        # see if we even have to crop
        if img.size == (width, height):
            return img

        left = (img.size[0] - width) / 2
        top = (img.size[1] - height) / 2
        right = left + width
        bottom = top + height

        return img.crop((left, top, right, bottom))

    @action
    def aresize(self, width, height, img_path=None, img=None, crop_img=True):
        """
        Thumbnail and crop, taking source and target aspect ratios into
        consideration. When source and target orientation is the same,
        scale to eliminate matting, and center-crop the image. When source
        and target dimensions have opposite orientation, scale to show the
        entire image without cropping, and matte. The former minimizes
        visually unattractive matting, and the latter eliminates center-crop
        body images. Due to contractual obligations, images are never
        increased in size and are instead matted if too small.

        :param width: desired width in pixels. required.
        :param height: desired height in pixels. required.
        :param img_path: a path to an image on the filesystem
        :param img: a PIL Image object
        :param crop_image: flag to turn off cropping. default True
        :returns: a PIL Image object
        """

        img = img or self.get_pil_from_path(img_path)
        if not img:
            raise ValueError('unable to find img given args')

        # If we're already the right size, don't do anything.
        if img.size == (width, height):
            return img

        source_width, source_height = img.size

        source_aspect = float(source_width) / source_height
        aspect = float(width) / height if width and height else source_aspect

        source_is_landscape = (source_aspect >= 1.0)
        is_landscape = (aspect >= 1.0)

        if source_is_landscape == is_landscape:
            if crop_img:
                # Source and target have the same orientation. Scale according to
                # aspect ratio to maximize photo area and minimize horizontal/
                # vertical border insertion.
                if source_aspect > aspect:
                    # Source has wider ratio than target. Scale to height.
                    target_width, target_height = None, height
                else:
                    # Source has taller ratio than target. Scale to width.
                    target_width, target_height = width, None
            else:
                # Source and target have the same orientation. Scale according to
                # aspect ratio and larger dimension to avoid cropping. This will
                # matte the image.
                if source_aspect > aspect:
                    # Source has wider ratio than target. Scale to width.
                    target_width, target_height = width, None
                else:
                    # Source has taller ratio than target. Scale to height.
                    target_width, target_height = None, height
        else: # crop_img is irrelevant here. The image won't be cropped regardless.
            # Source and target have opposite orientations. Scale to source's
            # longer dimension. This will not crop the image. This will matte
            # the image, but it will effectively maintain the visual
            # appearance of the source orientation.
            if source_is_landscape:
                target_width, target_height = width, None
            else:
                target_width, target_height = None, height

        # We never expand images. Resize only if the target is smaller.
        if ((target_width and target_width < source_width) or
                (target_height and target_height < source_height)):
            img = self.thumbnail(
                width = target_width,
                height = target_height,
                img = img
            )

        # see if we even have to crop
        if img.size == (width, height):
            return img

        # Create a new image of the target size, and paste the resized image
        # into it. This effectively mattes if necessary by pasting over the
        # matte background color, and it crops if necessary by pasting outside
        # the result image bounds.
        offset_x = (width - img.size[0]) / 2
        offset_y = (height - img.size[1]) / 2
        result = Image.new(mode='RGB', size=(width, height), color=MATTE_BACKGROUND_COLOR)
        result.paste(img, (offset_x, offset_y))
        return result

    @action
    def aresize_no_crop(self, width, height, img_path=None, img=None):
        """
        Thumbnail and fit into target area, taking source and target aspect
        ratios into consideration. Unless the target have the same aspect raio,
        this will create matting. the new image will retain it's original
        aspect ratio, and will be centered in the target area. Due to
        contractual obligations, images are never increased in size and are
        instead matted if too small.

        :param width: desired width in pixels. required.
        :param height: desired height in pixels. required.
        :param img_path: a path to an image on the filesystem
        :param img: a PIL Image object
        :returns: a PIL Image object
        """
        return self.aresize(width, height, img_path=img_path, img=img, crop_img=False)

    @action
    def matte(self, width, height, img_path=None, img=None):
        """
        Scale the image to fit in the given size, surrounded by a matte
        to fill in any extra space.

        :param width: desired width in pixels. required.
        :param height: desired height in pixels. required.
        :param img_path: a path to an image on the filesystem
        :param img: a PIL Image object
        :returns: a PIL Image object
        """

        if not (img or img_path):
            raise ValueError('unable to find img given args')
        img = img or self.get_pil_from_path(img_path)

        new_img = Image.new('RGB', (width, height), MATTE_BACKGROUND_COLOR)
        img.thumbnail((width, height), Image.ANTIALIAS)
        pos = ((width - img.size[0]) / 2, (height - img.size[1]) / 2)
        new_img.paste(img, pos)

        return new_img

    @action
    def thumbnail(self, width=None, height=None, img_path=None, img=None):
        """
        Scale in one dimension retaining image ratio in the other. Either width
        or height is required.

        :param width: desired width in pixels. mutually exclusive with height.
        :param height: desired height in pixels. mutually exclusive with width
        :param img_path: a path to an image on the filesystem
        :param img: a PIL Image object
        :returns: a PIL Image object
        """
        if not (img or img_path):
            raise ValueError('unable to find img given args')
        img = img or self.get_pil_from_path(img_path)

        if (width and height) or (width is None and height is None):
            raise ValueError('thumbnail requires width XOR height; got (%s, %s)' % (width, height))

        source_width = img.size[0]
        source_height = img.size[1]
        scale = lambda a,b,c: int(int(a) * float(b) / float(c))

        # we are guaranteed to have either height or width which lets us take
        # some validation shortcuts here.
        width = width or scale(source_width, height, source_height)
        height = height or scale(source_height, width, source_width)

        if width >= source_width or height >= source_height:
            return img

        return self.scale(width, height, img=img)

    @action
    def scale(self, width, height, img_path=None, img=None):
        """
        Scale to desired dimensions paying no attention to ratio.

        :param width: desired width in pixels. required.
        :param height: desired height in pixels. required.
        :param img_path: a path to an image on the filesystem
        :param img: a PIL Image object
        :returns: a PIL Image object
        """
        if not (img or img_path):
            raise ValueError('unable to find img given args')
        img = img or self.get_pil_from_path(img_path)

        if width > img.size[0]:
            width = img.size[0]

        if height > img.size[1]:
            height = img.size[1]

        # PIL is really bad at scaling GIFs. This helps a little with the quality.
        # (http://python.6.n6.nabble.com/Poor-Image-Quality-When-Resizing-a-GIF-tp2099779.html)
        if img.mode == "P":
            img = img.convert(mode="RGB", dither=Image.NONE)

        return img.resize((width, height), Image.ANTIALIAS)

    def get_pil_from_path(self, img_path):
        """
        given some path relative to MEDIA_ROOT, create a PIL Image and
        return it.

        :param img_path: a path to an image file relative to MEDIA_ROOT
        :raises IOError: if image is not found
        :return: PIL.Image
        """
        return Image.open(os.path.join(settings.MEDIA_ROOT, img_path))

    def cache_key(self, *args):
        """
        Compute a unique cache key for an image operation. Takes width, height,
        fs path, desired action, and quality into account.
        """
        key_string = u':'.join(map(unicode, args))
        hashed = md5(key_string).hexdigest()
        return 'lazythumbs:{0}'.format(hashed)

    def two_hundred(self, img_data, img_format):
        """
        Generate a 200 image response with raw image data, Cache-Control set,
        and an image/{img_format} content-type.

        :param img_data: raw image data as a string
        """
        resp = HttpResponse(img_data, content_type='image/%s' % img_format.lower())
        resp['Cache-Control'] = 'public,max-age=%s' % settings.LAZYTHUMBS_CACHE_TIMEOUT
        return resp

    def four_oh_four(self):
        """
        Generate a 404 response with an image/jpeg content_type. Sets a
        Cache-Control header for caches like Akamai (browsers will ignore it
        since it's a 4xx.
        """
        resp = HttpResponse(status=404, content_type='image/jpeg')
        resp['Cache-Control'] = 'public,max-age=%s' % settings.LAZYTHUMBS_404_CACHE_TIMEOUT
        return resp
