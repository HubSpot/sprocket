from datetime import datetime
import inspect
import time
from unittest import TestCase

from django.conf import settings
from django.conf.urls.defaults import patterns, include, url
from django.test.client import Client
from django.utils import simplejson

from mocking_bird.mocking import MockingBirdMixin

from ..mixins import BaseMixin
from ..auth import NoAuthentication
from ..fields import DateTimeField, ApiField
from ..base_resource import BaseApiResource, ResourceMeta, EndPoint, ArgFilters, POST, PUT, GET, UserError, UnauthenticatedError


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
        self.assertTrue(data['pk'] > 10000)
        self.assertEquals(r['x-sprocket-new-object-id'], str(data['pk']))

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

    def test_mixins(self):
        c = Client()

        label = 'ATestLabel'

        post_data = {
            'label': label,
            }

        r = c.post(
            '/api/simple-resource',
            data=simplejson.dumps(post_data),
            content_type='application/json')
        data = simplejson.loads(r.content)

        r = c.post(
            '/api/simple-resource/%s/soft-delete' % data['pk'],
            content_type='application/json')
        self.assertEquals(200, r.status_code)

        r = c.get(
            '/api/simple-resource/%s' % data['pk'],
            content_type='application/json')
        self.assertEquals(200, r.status_code)
        data = simplejson.loads(r.content)
        # The created timestamp should not have the default 1900 value
        self.assertTrue('1900' not in data['created'] and '201' in data['created'])
        # Verify the soft-delete worked
        self.assertTrue(data['deleted'] == True)

    def test_error_handling(self):
        c = Client()

        label = 'ATestLabel'

        post_data = {
            'label': label,
            }
        r = c.post(
            '/api/simple-resource',
            data=simplejson.dumps(post_data),
            content_type='application/json')
        data = obj_data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)

        r = c.put(
            '/api/simple-resource/%s' % data['pk'],
            data=simplejson.dumps({'nicknames': ['a', 'b', 'c', 'd', 'e', 'f']}),
            content_type='application/json')
        data = simplejson.loads(r.content)
        self.assertEquals(400, r.status_code)

        # Illegal method
        r = c.delete(
            '/api/simple-resource',
            content_type='application/json')
        self.assertEquals(405, r.status_code)

        r = c.get('/api/simple-resource/%s?denyMe=true' % obj_data['pk'])
        self.assertEquals(403, r.status_code)

    url_conf = 'sprocket.test.test_base_resource'

    def setUp(self):
        super(SimpleCase, self).setUp()
        self.org_urls = settings.ROOT_URLCONF
        settings.ROOT_URLCONF = self.url_conf
        simple_resource._storage = {}

    def tearDown(self):
        super(SimpleCase, self).tearDown()
        settings.ROOT_URLCONF = self.org_urls


class SimpleObject(object):
    pk = 0
    label = ''
    city = ''
    created = datetime(1900, 1, 1)
    updated = datetime(1900, 1, 1)
    published_at = datetime.utcnow()
    nicknames = ()
    deleted = False

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class SimpleResource(BaseApiResource):
    _storage = {}

    class Meta(ResourceMeta):
        resource_name = 'simple-resource'
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
                GET('list', ArgFilters.fields_from_query),
                POST('create', ArgFilters.fields_from_json)
                ),
            EndPoint(
                r"^(?P<resource_name>%s)/(?P<pk>[\d]+)$" % self._meta.resource_name,
                GET('get', ArgFilters.fields_from_query),
                PUT('update', ArgFilters.fields_from_json)
                ),
            ]
        return endpoints

    def get_mixins(self):
        return [DeletedUpdatedMixin(self)]

    def update(self, pk, **kwargs):
        if len(kwargs.get('nicknames', [])) > 5:
            raise UserError("Too many nicknames", 400)
        obj = self._storage[long(pk)]
        for field in self.fields:
            if field.name in kwargs:
                field.dict_to_obj(kwargs, obj)
        self.execute_handlers('updated', obj)
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
        for field in self.fields:
            if field.name in kwargs:
                field.dict_to_obj(kwargs, obj)
        obj.pk = long(time.time() * 1000)
        self.execute_handlers('created', obj)
        self._storage[obj.pk] = obj
        self.set_response_header('x-sprocket-new-object-id', str(obj.pk))
        return obj

    def delete(self, pk):
        del self._storage[long(pk)]
        self.execute_handlers('deleted', long(pk))

    def on_authenticate(self, request):
        if request.GET.get('denyMe') == 'true':
            raise UnauthenticatedError("denyMe was true")


class DeletedUpdatedMixin(BaseMixin):
    def get_endpoints(self):
        return [
            EndPoint(
                r"^(?P<resource_name>%s)/(?P<pk>[\d]+)/soft-delete$" % self.api._meta.resource_name,
                POST('soft_delete'))
            ]

    def on_created(self, obj):
        obj.created = datetime.utcnow()

    def soft_delete(self, pk):
        self.api._storage[long(pk)].deleted = True
        return True


simple_resource = SimpleResource()
urlpatterns = patterns('',
    (r'^api/', include(simple_resource.urls)),
)
