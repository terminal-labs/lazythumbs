import errno
import os
import shutil
import tempfile
from unittest import TestCase

from mock import Mock, patch

from lazythumbs.views import LazyThumbRenderer, action
from lazythumbs.urls import urlpatterns
from django.core.urlresolvers import reverse, resolve


TEST_IMG_GIF = os.path.join(os.path.dirname(__file__), "testdata", "testimage.gif")

class MockCache(object):
    def __init__(self):
        self.cache = {}

    def set(self, key, value, expiration=None):
        self.cache[key] = value

    def get(self, key, default=None):
        return self.cache.get(key)


class MockImg(object):
    def __init__(self, width=1000, height=1000):
        self.called = []
        self.size = (width, height)
        self.mode = "RGB"

    def resize(self, size, _):
        self.called.append('resize')
        self.size = size
        return self

    def crop(self, dimensions):
        self.called.append('crop')
        return self


class TestMatte(TestCase):

    def test_new_img(self):
        renderer = LazyThumbRenderer()
        new_img = renderer.matte(200, 200, img_path=TEST_IMG_GIF)
        self.assertEqual(new_img.size, (200, 200))

    def test_no_img(self):
        renderer = LazyThumbRenderer()
        self.assertRaises(ValueError, renderer.matte, 200, 200)


class TestScale(TestCase):

    def test_maximum_width_and_height(self):
        renderer = LazyThumbRenderer()
        new_img = renderer.scale(1000, 1000, img_path=TEST_IMG_GIF)
        self.assertEqual(new_img.size, (399, 499))

    def test_no_img(self):
        renderer = LazyThumbRenderer()
        self.assertRaises(ValueError, renderer.scale, 200, 200)


class RenderTest(TestCase):
    """ test image rendering process """

    def test_action_decorator(self):
        """
        Ensure the decorator causes an action to show up in
        _allowed_actions
        """
        class MyRenderer(LazyThumbRenderer):
            @action
            def myaction(self):  # pragma: no cover
                pass

        renderer = MyRenderer()
        self.assertTrue('myaction' in renderer.allowed_actions)

    def test_thumbnail_noop(self):
        """
        Test that no image operations occur if the desired w/h match image's
        existing w/h
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg()
        mock_img.size = (100, 100)
        img = renderer.thumbnail(width=100, img=mock_img)
        self.assertEqual(img.size[0], 100)
        self.assertEqual(img.size[1], 100)
        self.assertEqual(len(mock_img.called), 0)

    def test_thumbnail_no_img(self):
        renderer = LazyThumbRenderer()
        self.assertRaises(ValueError, renderer.thumbnail, 200, 200)

    def test_thumbnail_square(self):
        """
        Test behavior of thumbnail action when no width == height
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg()
        mock_img.size = (100, 100)
        img = renderer.thumbnail(width=50, img=mock_img)
        self.assertEqual(img.size[0], 50)
        self.assertEqual(img.size[1], 50)
        self.assertEqual(len(mock_img.called), 1)
        self.assertTrue('resize' in mock_img.called)

    def test_thumbnail_width_and_height_specified(self):
        renderer = LazyThumbRenderer()
        mock_img = MockImg()
        mock_img.size = (100, 100)
        self.assertRaises(ValueError, renderer.thumbnail, width=50, height=50, img=mock_img)

    def test_thumbnail_no_width_and_no_height_specified(self):
        renderer = LazyThumbRenderer()
        mock_img = MockImg()
        mock_img.size = (100, 100)
        self.assertRaises(ValueError, renderer.thumbnail, img=mock_img)

    def test_thumbnail_no_upscaling(self):
        """
        Ensure that upscaling is forbidden in thumbnail action.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg()
        mock_img.size = (100, 100)
        img = renderer.thumbnail(width=20000, img=mock_img)

        self.assertEqual(img.size[0], 100)
        self.assertEqual(img.size[1], 100)
        self.assertEqual(len(mock_img.called), 0)

    def test_resize(self):
        """
        Test behavior of resize action.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg()
        img = renderer.resize(width=48, height=50, img=mock_img)
        self.assertEqual(img.size[1], 50)
        self.assertEqual(len(mock_img.called), 2)
        self.assertTrue('crop' in mock_img.called)
        self.assertTrue('resize' in mock_img.called)

    def test_resize_no_img(self):
        renderer = LazyThumbRenderer()
        self.assertRaises(ValueError, renderer.resize, 200, 200)

    def test_resize_no_upscaling(self):
        """
        Ensure upscaling is forbidden in resize action.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg()
        img = renderer.resize(width=2000, height=2000, img=mock_img)

        self.assertEqual(img.size[0], 1000)
        self.assertEqual(img.size[1], 1000)
        self.assertEqual(len(mock_img.called), 0)

    def test_aresize_width(self):
        """
        Ensure landscape aresize action thumbnails to width and center-crops.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=1500, height=1000)
        mock_Image = Mock()

        # aresize 1500x1000 => 750x400 should thumbnail to 750x500 and then
        # paste into the center of a new image, losing some top/bottom content.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize(width=750, height=400, img=mock_img)

        self.assertEqual(mock_img.called, ['resize'])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (750, 400))
        img.paste.assert_called_once_with(mock_img, (0, -50))

    def test_aresize_height(self):
        """
        Ensure landscape aresize action thumbnails to height and center-crops.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=2000, height=1000)
        mock_Image = Mock()

        # aresize 2000x1000 => 1000x800 should thumbnail to 1600x800 and then
        # paste into the center of a new image, losing some left/right content.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize(width=1000, height=800, img=mock_img)

        self.assertEqual(mock_img.called, ['resize'])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (1000, 800))
        img.paste.assert_called_once_with(mock_img, (-300, 0))

    def test_aresize_portrait(self):
        """
        Ensure aresize action from portrait to landscape shrinks image and
        mattes sides.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=1000, height=2000)
        mock_Image = Mock()

        # aresize 1000x2000 => 600x500 should thumbnail to 250x500 and then
        # paste into the center of a new image, leaving matte background
        # content on the sides.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize(width=600, height=500, img=mock_img)

        self.assertEqual(mock_img.called, ['resize'])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (600, 500))
        img.paste.assert_called_once_with(mock_img, (175, 0))

    def test_aresize_small(self):
        """
        Ensure aresize action does not grow a small image.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=100, height=80)
        mock_Image = Mock()

        # aresize 100x80 => 300x200 should not resize, but should paste
        # into the center of a new image, leaving matte background content
        # on the sides.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize(width=300, height=200, img=mock_img)

        self.assertEqual(mock_img.called, [])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (300, 200))
        img.paste.assert_called_once_with(mock_img, (100, 60))

    def test_aresize_no_crop_same_orientation_wider_aspect_ratio(self):
        """
        Ensure aresize_no_crop action when the source and target are the
        same orientation, and the source has a wider aspect ratio, that it
        scales according to width and mattes the top and bottom.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=2000, height=1000)
        mock_Image = Mock()

        # aresize_no_crop 2400x1000 => 600x500 should thumbnail to 600x250 and
        # then paste into the center of a new image, leaving matte background
        # content on the top and bottom.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize_no_crop(width=600, height=500, img=mock_img)

        self.assertEqual(mock_img.called, ['resize'])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (600, 500))
        img.paste.assert_called_once_with(mock_img, (0, 100))

    def test_aresize_no_crop_same_orientation_taller_aspect_ratio(self):
        """
        Ensure aresize_no_crop action when the source and target are the
        same orientation, and the source has a taller aspect ratio, that it
        scales according to height and mattes the sides.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=1000, height=2000)
        mock_Image = Mock()

        # aresize_no_crop 1000x2400 => 500x600 should thumbnail to 600x250 and
        # then paste into the center of a new image, leaving matte background
        # content on the top and bottom.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize_no_crop(width=500, height=600, img=mock_img)

        self.assertEqual(mock_img.called, ['resize'])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (500, 600))
        img.paste.assert_called_once_with(mock_img, (100, 0))

    def test_aresize_no_crop_opposite_orientation_landscape(self):
        """
        Ensure aresize_no_crop action when the source and target are the
        opposite orientation, and the source is landscape, that it scales
        according to width and mattes the top and bottom.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=2000, height=1000)
        mock_Image = Mock()

        # aresize_no_crop 2000x1000 => 500x600 should thumbnail to 500x250 and
        # then paste into the center of a new image, leaving matte background
        # content on the top and bottom.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize_no_crop(width=500, height=600, img=mock_img)

        self.assertEqual(mock_img.called, ['resize'])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (500, 600))
        img.paste.assert_called_once_with(mock_img, (0, 175))

    def test_aresize_no_crop_opposite_orientation_portrait(self):
        """
        Ensure aresize_no_crop action when the source and target are the
        opposite orientation, and the source is portrait, that it scales
        according to height and mattes sides.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=1000, height=2000)
        mock_Image = Mock()

        # aresize_no_crop 1000x2000 => 600x500 should thumbnail to 250x500 and
        # then paste into the center of a new image, leaving matte background
        # content on the sides.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize_no_crop(width=600, height=500, img=mock_img)

        self.assertEqual(mock_img.called, ['resize'])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (600, 500))
        img.paste.assert_called_once_with(mock_img, (175, 0))

    def test_aresize_no_crop_small(self):
        """
        Ensure aresize_no_crop action does not grow a small image.
        """
        renderer = LazyThumbRenderer()
        mock_img = MockImg(width=100, height=80)
        mock_Image = Mock()

        # aresize_no_crop 100x80 => 300x200 should not resize, but should paste
        # into the center of a new image, leaving matte background content
        # on the sides.
        with patch('lazythumbs.views.Image', mock_Image):
            img = renderer.aresize(width=300, height=200, img=mock_img)

        self.assertEqual(mock_img.called, [])
        self.assertEqual(img, mock_Image.new.return_value)
        self.assertEqual(mock_Image.new.call_args[1]['size'], (300, 200))
        img.paste.assert_called_once_with(mock_img, (100, 60))


class GetViewTest(TestCase):
    """ Test behavior of LazyThumbRenderer.get """

    def mc_factory(self, was_404):
        """
        churn out mocked caches with a preset .get(). Also a rapper?
        """
        mc = Mock()
        ret = was_404
        mc.get = Mock(return_value=ret)
        mc.set = Mock()
        return mc

    def setUp(self):
        self.renderer = LazyThumbRenderer()
        self.mock_Image = Mock()
        self.mock_img = Mock()
        self.mock_Image.open = Mock(return_value=self.mock_img)
        self.mock_img.size = [1,1]

    def test_img_404_warm_cache(self):
        """
        Ensure we go straight to a 404 response without setting anything new in
        cache or touching filesystem if we encounter a cached 404.
        """
        req = Mock()
        req.path = "/lt_cache/thumbnail/48/i/p.jpg"
        self.renderer._render_and_save = Mock()
        with patch('lazythumbs.views.cache', self.mc_factory(1)) as mc:
            resp = self.renderer.get(req, 'thumbnail', '48', 'i/p')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp['Content-Type'], 'image/jpeg')
        self.assertTrue('Cache-Control' in resp)
        self.assertFalse(mc.set.called)

    def test_img_404_cold_cache(self):
        """
        Basic 404: requested image is not found. Make sure proper response
        headers are set and the 404 was cached.
        """
        req = Mock()
        req.path = "/lt_cache/thumbnail/48/i/p.jpg"
        with patch('lazythumbs.views.cache', MockCache()) as mc:
            resp = self.renderer.get(req, 'thumbnail', '48', 'i/p')
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp['Content-Type'], 'image/jpeg')
        self.assertTrue('Cache-Control' in resp)
        self.assertEqual(len(mc.cache.keys()), 1)
        key = mc.cache.keys()[0]
        cached = mc.cache[key]
        self.assertEqual(cached, 1)

    def test_img_200_cold_cache(self):
        """
        Pretend we found the requested rendered image on the filesystem. Ensure
        proper response headers are set and the rendered path was cached.
        """
        req = Mock()
        req.path = "/lt_cache/thumbnail/48/i/p.jpg"
        self.renderer.fs.save = Mock()
        with patch('lazythumbs.views.Image', self.mock_Image):
            with patch('lazythumbs.views.cache', MockCache()) as mc:
                resp = self.renderer.get(req, 'thumbnail', '48', 'i/p')

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'image/jpeg')
        self.assertTrue('Cache-Control' in resp)
        self.assertEqual(resp.content, '') # empty buffer means raw_data is ''
        self.assertEqual(len(mc.cache.keys()), 1)

        key = mc.cache.keys()[0]
        cached = mc.cache[key]
        self.assertEqual(cached, False)

    def test_no_img_should_404(self):
        """
        When save fails with EEXIST error, it will try to read the file again
        But if it still can't be read, make sure it returns a 404 instead of 0-byte image.
        """
        req = Mock()
        req.path = "/lt_cache/thumbnail/48/i/p.jpg"
        self.renderer.fs.save = Mock()
        err = OSError()
        err.errno = errno.EEXIST
        self.renderer.fs.save.side_effect = err
        with patch('lazythumbs.views.Image', self.mock_Image):
            with patch('lazythumbs.views.cache', MockCache()):
                resp = self.renderer.get(req, 'thumbnail', '48', 'i/p')
        self.assertEqual(resp.status_code, 404)

    def test_naughty_paths_root(self):
        resp = self.renderer.get(None, 'thumbnail', '48', '/')
        self.assertEqual(resp.status_code, 404)

    def test_naughty_paths_traverse(self):
        resp = self.renderer.get(None, 'thumbnail', '48', '../')
        self.assertEqual(resp.status_code, 404)

    def test_invalid_action(self):
        resp = self.renderer.get(None, 'invalid_action', '48', 'i/p')
        self.assertEqual(resp.status_code, 404)

    def test_invalid_geometry(self):
        resp = self.renderer.get(None, 'thumbnail', '48x48x48', 'i/p')
        self.assertEqual(resp.status_code, 404)


class TestOddFiles(TestCase):

    def test_extensionless_gif(self):
        """If the image file is a GIF without an extension, we can produce
        a valid thumbnail for it."""

        # Note: this test image file was breaking thumbnails if lazythumbs didn't
        # see the .gif extension.  I tried creating a gif on the fly using
        # PIL but didn't hit the same problem, so it might be something about
        # this image that's special, maybe that it has a transparent background.
        # (The error was "cannot write mode P as JPEG"; the symptom was a 404
        # response.)

        MEDIA_ROOT = tempfile.gettempdir()

        # Need to override MEDIA_ROOT in both django file storage and lazythumbs views
        # and Django doesn't provide override_settings until 1.4
        with patch('django.core.files.storage.settings') as settings1:
            settings1.MEDIA_ROOT = MEDIA_ROOT

            with patch('lazythumbs.views.settings') as settings2:
                settings2.MEDIA_ROOT = MEDIA_ROOT

                testfile = TEST_IMG_GIF
                filename = None
                try:
                    filename = os.path.join(MEDIA_ROOT, "gif_without_extension")
                    shutil.copy(testfile, filename)
                    # Now we have a gif file in a filename that doesn't end in .gif

                    renderer = LazyThumbRenderer()
                    source_path = os.path.relpath(filename, MEDIA_ROOT)
                    rsp = renderer.get(
                        request=Mock(path="/thumbnail/x50/" + source_path),
                        action="thumbnail",
                        geometry="x50",
                        source_path=source_path
                        )
                    # if you get 404, jpeg encoder is probably missing for Pillow
                    self.assertEqual(200, rsp.status_code)
                finally:
                    if filename:
                        os.remove(filename)


def test_paths(routes_to_test=()):
    for route in routes_to_test:
        path = route["url_path"]
        pattern = route["pattern_name"]

        # if kwparams:
        #     yield reverse(pattern, kwargs=kwparams), path
        # else:
        #     yield reverse(pattern), path

        yield resolve(path).url_name, pattern


class TestUrlMatching(TestCase):
    """
    Test that urls that are built by the template tag are properly matched by
    the lazythumbs.urls.urlpatterns
    """

    def setUp(self):
        self.routes_to_test = (
            {'url_path':'/lt/lt_cache/resize/5/p/i.jpg', 'pattern_name':'lt_slash_sep'},
            {'url_path':'/lt/lt_cache/resize/5/q80/p/i.jpg', 'pattern_name':'lt_slash_sep_w_quality'},
            {'url_path':'/lt/lt_cache/resize/5/5/p/i.jpg', 'pattern_name':'lt_slash_sep'},
            {'url_path':'/lt/lt_cache/resize/5/5/q80/p/i.jpg', 'pattern_name':'lt_slash_sep_w_quality'},
            {'url_path':'/lt/lt_cache/resize/5x5/p/i.jpg', 'pattern_name':'lt_x_sep'},
            {'url_path':'/lt/lt_cache/resize/5x5/q80/p/i.jpg', 'pattern_name':'lt_x_sep_w_quality'},
            {'url_path':'/lt/lt_cache/resize/x/5/p/i.jpg', 'pattern_name':'lt_x_width'},
            {'url_path':'/lt/lt_cache/resize/x/5/q80/p/i.jpg', 'pattern_name':'lt_x_width_w_quality'},
        )

    @patch('django.conf.settings')
    def test_url_matching(self, settings):
        settings.ROOT_URLCONF = urlpatterns
        settings.USE_I18N = False
        routes_tested = 0
        for path1, path2 in test_paths(self.routes_to_test):
            routes_tested += 1
            self.assertEqual(path1, path2)
        self.assertEqual(routes_tested, 8)
