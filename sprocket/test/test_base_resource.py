from datetime import datetime
import inspect
import time
from unittest import TestCase

from django.conf import settings
from django.conf.urls.defaults import patterns, include, url
from django.test.client import Client
from django.utils import simplejson

from mocking_bird.mocking import MockingBirdMixin

from ..auth import NoAuthentication
from ..fields import DateTimeField, ApiField
from ..base_resource import BaseApiResource, ResourceMeta, EndPoint, RequestKwargFilters


class SimpleCase(TestCase, MockingBirdMixin):
    def test_direct_crud(self):
        resource = SimpleResource()
        dt = datetime(2011, 4, 1, 12, 30, 0)
        label = 'ATestLabel'
        nicknames = ['jack', 'jacko']
        obj = resource.create(label=label, published_at=dt, nicknames=nicknames)
        
        obj2 = resource.get(pk=obj.pk)
        self.assertEquals(label, obj2.label)
        self.assertEquals(nicknames, obj2.nicknames)


        new_label = 'ANewLabel'
        resource.update(obj.pk, label=new_label)
        obj3 = resource.get(pk=obj.pk)
        self.assertEquals(new_label, obj3.label)

    def test_http_crud(self):
        c = Client()

        dt = datetime(2011, 4, 1, 12, 30, 0)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')
        label = 'ATestLabel'
        nicknames = ['jack', 'jacko']

        post_data = {
            'label': label,
            'published_at': dt_str,
            'nicknames': nicknames
            }

        r = c.post(
            '/api/simple-resource',
            data=simplejson.dumps(post_data),
            content_type='application/json')
        self.assertEquals(200, r.status_code)
        data = simplejson.loads(r.content)
        r = c.get(
            '/api/simple-resource/%s' % data['pk'],
            content_type='application/json')
        self.assertEquals(200, r.status_code)
        data = simplejson.loads(r.content)
        self.assertEquals(label, data['label'])
        

        new_label = 'NewLabel'
        post_data['label'] = new_label
        r = c.put(
            '/api/simple-resource/%s' % data['pk'],
            data=simplejson.dumps(post_data),
            content_type='application/json')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(new_label, data['label'])

        r = c.get(
            '/api/simple-resource',
            content_type='application/json')
        self.assertEquals(200, r.status_code)
        data = simplejson.loads(r.content)
        self.assertEquals(1, len(data))



    url_conf =  'sprocket.test.test_base_resource'
    def setUp(self):
        super(SimpleCase, self).setUp()
        self.org_urls = settings.ROOT_URLCONF
        settings.ROOT_URLCONF = self.url_conf

    def tearDown(self):
        super(SimpleCase, self).tearDown()
        settings.ROOT_URLCONF = self.org_urls



class SimpleObject(object):
    pk = 0
    label = ''
    city = ''
    published_at = datetime.utcnow()
    nicknames = ()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class SimpleResource(BaseApiResource):
    _storage = {}

    class Meta(ResourceMeta):
        resource_name = 'simple-resource'
        authentication = NoAuthentication()
        model_class = SimpleObject

    def on_init_fields(self, fields):
        for name in dir(SimpleObject):
            attr = getattr(SimpleObject, name)
            if name.startswith('_'):
                continue
            if callable(attr):
                continue
            if isinstance(attr, datetime):
                cls = DateTimeField
            else:
                cls = ApiField
            fields.append(cls(name))

    def get_endpoints(self):
        endpoints = [
            EndPoint(
                r"^(?P<resource_name>%s)$" % self._meta.resource_name,
                #r".*",
                GET='list',
                POST='create',
                kwargs_filters=[
                    RequestKwargFilters.from_get_params,
                    RequestKwargFilters.from_json
                    ]
                ),
            EndPoint(
                r"^(?P<resource_name>%s)/(?P<pk>[\d]+)$" % self._meta.resource_name,
                GET='get',
                PUT='update',
                kwargs_filters=[
                    RequestKwargFilters.from_get_params,
                    RequestKwargFilters.from_json
                    ]
                ),
            ]
        return endpoints

    def update(self, pk, **kwargs):
        obj = self._storage[long(pk)]
        for field in self._fields:
            if field.name in kwargs:
                field.dict_to_obj(kwargs, obj)
        return obj

    def get(self, pk):
        o = self._storage[long(pk)]
        return o

    def list(self, **kwargs):
        items = []
        for item in self._storage.values():
            filter_out = False
            if kwargs:
                for key, val in kwargs.items():
                    if getattr(item, 'key', None) != val:
                        filter_out = True
                        break
            if not filter_out:
                items.append(item)
        return items

    def create(self, **kwargs):
        obj = SimpleObject()
        for field in self._fields:
            if field.name in kwargs:
                field.dict_to_obj(kwargs, obj)
        obj.pk = long(time.time() * 1000)
        self._storage[obj.pk] = obj
        return obj

    def on_authenticate(self, request):
        pass


simple_resource = SimpleResource()
urlpatterns = patterns('',
    (r'^api/', include(simple_resource.urls)),
)
