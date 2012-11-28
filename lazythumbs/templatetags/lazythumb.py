"""
    {% lazythumb image.url thumbnail '48' as img_tag %}
        <img src="{{img_tag.src}}" width="{{img_tag.width}}" height="{{img_tag.height}} />
    {% endlazythumb %}
    {% lazythumb image.url resize '150x200' %}
        <img src="{{img_tag.src}}" width="{{img_tag.width}}" height="{{img_tag.height}} />
    {% endlazythumb %}
"""
import logging
import re
import json

from django.template import TemplateSyntaxError, Library, Node, Variable
from lazythumbs.util import compute_img, get_attr_string, get_placeholder_url, get_source_img_attrs


# TODO this should *not* be hardcoded. it completely prevents the proper
# utilization of the subclassing feature of the renderer. A bug, imo.
SUPPORTED_ACTIONS = ['thumbnail', 'resize']

register = Library()
logger = logging.getLogger()

register.tag('lazythumb', lambda p, t: LazythumbNode(p, t))
class LazythumbNode(Node):
    usage = 'Expected invocation is {% lazythumb url|ImageFile|Object action geometry as variable %}'

    def __init__(self, parser, token):
        # simple alias
        tse = lambda m: TemplateSyntaxError('lazythumb: %s' % m)
        bits = token.contents.split()
        try:
            _, thing, action, geometry, _, as_var = bits
        except ValueError:
            raise tse(self.usage)

        self.as_var = as_var

        if action not in SUPPORTED_ACTIONS:
            raise tse('supported actions are %s' % SUPPORTED_ACTIONS)
        self.action = action

        self.thing = Variable(thing)
        self.geometry = Variable(geometry)

        self.nodelist = parser.parse(('endlazythumb',))
        parser.delete_first_token()

    def render(self, context):

        thing = self.thing.resolve(context)
        action = self.action
        geometry = self.geometry.resolve(context)

        context.push()
        context[self.as_var] = compute_img(thing, action, geometry)
        output = self.nodelist.render(context)
        context.pop()
        return output


register.tag('img_attrs', lambda p, t: ImgAttrsNode(p, t))
class ImgAttrsNode(Node):
    usage = 'Expected invocation is {% img_attrs img %} where img is the img attrs set by the lazythumb tag'

    def __init__(self, parser, token):
        try:
            _, img = token.contents.split()
        except ValueError:
            raise TemplateSyntaxError('img_attrs: %s' % self.usage)
        self.img_var = Variable(img)

    def render(self, context):
        return get_attr_string(self.img_var.resolve(context))


register.tag('lt_clientside', lambda p, t: ClientSideNode(p, t))
class ClientSideNode(Node):
    """
    Used in script tag to output an object literal containing the lt_cache img src
    with placeholders for lazythumb action (resize|thumbnail) and dimensions.
    Invoke like so: var img = {% lt_clientside photo_obj %};
    Outputs: var img = {
        "width": 400,
        "height": 300,
        "src": "/media/lt/lt_cache/{action}/{dimensions}/path/to/img.jpg"
    };
    """
    usage = 'Expected invocation is {% lt_clientside url|ImageFile|Object %}'

    def __init__(self, parser, token):
        tse = lambda m: TemplateSyntaxError('lt_clientside: %s' % m)
        bits = token.contents.split()
        try:
            _, thing = bits
        except ValueError:
            raise tse(self.usage)
        self.thing = Variable(thing)

    def render(self, context):
        thing = self.thing.resolve(context)
        img_data = get_source_img_attrs(thing)
        img_data['src'] = get_placeholder_url(thing)
        return json.dumps(img_data)
