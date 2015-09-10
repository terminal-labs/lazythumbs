try:
    from django.conf.urls import patterns, url
except ImportError:
    from django.conf.urls.defaults import patterns, url  # support Django 1.3

from lazythumbs.views import LazyThumbRenderer

urlpatterns = patterns('',
    # we'll cleanse the liberal .+ in the view.
    url(r'lt_cache/(?P<action>\w+)/(?P<geometry>\d+/\d+|\d+)/(?P<quality>q\d+)/(?P<source_path>.+)$', LazyThumbRenderer.as_view(), name='lt_slash_sep_w_quality'),
    url(r'lt_cache/(?P<action>\w+)/(?P<geometry>\d+/\d+|\d+)/(?P<source_path>.+)$', LazyThumbRenderer.as_view(), name='lt_slash_sep'),

    url(r'lt_cache/(?P<action>\w+)/(?P<geometry>\d+x\d+)/(?P<quality>q\d+)/(?P<source_path>.+)$', LazyThumbRenderer.as_view(), name='lt_x_sep_w_quality'),
    url(r'lt_cache/(?P<action>\w+)/(?P<geometry>\d+x\d+)/(?P<source_path>.+)$', LazyThumbRenderer.as_view(), name='lt_x_sep'),


    url(r'lt_cache/(?P<action>\w+)/(?P<geometry>x/\d+)/(?P<quality>q\d+)/(?P<source_path>.+)$', LazyThumbRenderer.as_view(), name='lt_x_width_w_quality'),
    url(r'lt_cache/(?P<action>\w+)/(?P<geometry>x/\d+)/(?P<source_path>.+)$', LazyThumbRenderer.as_view(), name='lt_x_width'),
)
