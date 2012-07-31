

from datetime import datetime
import inspect
import time
from unittest import TestCase

from django.conf import settings
from django.conf.urls.defaults import patterns, include, url
from django.db.models import Model, CharField, DateTimeField as DjDateTimeField, EmailField, IntegerField
from django.db import connections, transaction
from django.test.client import Client
from django.utils import simplejson

from mocking_bird.mocking import MockingBirdMixin

from ..mixins import BaseMixin
from ..auth import NoAuthentication
from ..fields import DateTimeField, ApiField
from ..django_model_resource import DjangoModelResource
from ..base_resource import BaseApiResource, ResourceMeta, EndPoint, ArgFilters, POST, PUT, GET


class SimpleCase(TestCase, MockingBirdMixin):
    def test_direct_crud(self):
        label = 'MyLabelz'
        email = 'amail@maila.com'
        second_label = 'MySecondLabel'
        obj = my_resource.create(
            label=label,
            email=email)
        obj = my_resource.get(pk=obj.pk)
        self.assertEquals(label, obj.label)

        obj = my_resource.get(email=email)
        self.assertEquals(label, obj.label)

        second_label = 'MySecondLabel'
        obj = my_resource.create(
            label=second_label)

        objs = my_resource.list()
        self.assertEquals(2, len(objs))


    def test_http_crud(self):
        c = Client()
        label = 'MyLabelz'
        new_label = 'NewMylabelszz'
        email = 'amail@maila.com'
        second_label = 'MySecondLabel'
        age = 17
        dt = datetime(2011, 7, 1, 12, 30, 0)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')

        post_data = {
            'label': label,
            'published_at': dt_str,
            'age': age, 
            'email': email
            }
        
        # Create an object
        r = c.post(
            '/api/my-resource/',
            data=simplejson.dumps(post_data),
            content_type='application/json')
        self.assertEquals(200, r.status_code)
        data = simplejson.loads(r.content)
        obj_data = data
        self.assertTrue(data['id'] > 10000)

        # Now get the object we just created
        r = c.get('/api/my-resource/%s/' % data['id'])
        self.assertEquals(200, r.status_code)
        data = simplejson.loads(r.content)
        self.assertTrue(label, data['label'])
        self.assertTrue(dt_str, data['published_at'])

        # Update the object
        post_data['label'] = new_label
        r = c.put(
            '/api/my-resource/%s/' % data['id'],
            data=simplejson.dumps(post_data),
            content_type='application/json')
        self.assertEquals(200, r.status_code)
        data = simplejson.loads(r.content)
        self.assertTrue(new_label, data['label'])

        # Post a second object
        r = c.post(
            '/api/my-resource/',
            data=simplejson.dumps(post_data),
            content_type='application/json')
        self.assertEquals(200, r.status_code)

        # The list should now have two objects
        r = c.get('/api/my-resource/')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(2, len(data['objects']))
        self.assertEquals(2, data['total_count'])

        r = c.get('/api/my-resource/?offset=1')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(1, len(data['objects']))
        self.assertEquals(2, data['total_count'])


        # Delete the object
        r = c.delete(
            '/api/my-resource/%s/' % obj_data['id'],
            content_type='application/json')
        self.assertEquals(200, r.status_code)

        r = c.get('/api/my-resource/%s/' % obj_data['id'])
        self.assertEquals(404, r.status_code)


    url_conf =  'sprocket.test.test_django_model_resource'
    def setUp(self):
        super(SimpleCase, self).setUp()
        self.org_urls = settings.ROOT_URLCONF
        settings.ROOT_URLCONF = self.url_conf
        _create_table()

    def tearDown(self):
        super(SimpleCase, self).tearDown()
        settings.ROOT_URLCONF = self.org_urls

class FakeModel(Model):
    id = IntegerField(primary_key=True)
    label = CharField()
    created = DjDateTimeField(auto_now_add=True)
    updated = DjDateTimeField(auto_now_add=False)
    published_at = DjDateTimeField()
    email = EmailField()
    age = IntegerField()

    def save(self):
        if not self.pk:
            self.pk = long(time.time()*1000)
        super(FakeModel, self).save()

    class Meta:
        db_table = 'sprocket_test_fake_model'

class MyModelResource(DjangoModelResource):

    class Meta(ResourceMeta):
        resource_name = 'my-resource'
        model_class = FakeModel

    def on_authenticate(self, request):
        pass


def _create_table():
    sql1 = """DROP TABLE IF EXISTS sprocket_test_fake_model"""
    sql2 = """
    CREATE TABLE sprocket_test_fake_model (
        id INTEGER PRIMARY KEY ASC, 
        label, 
        published_at DATETIME,
        created DATETIME,
        updated DATETIME,
        email,
        age INTEGER);
    """
    cursor = connections['default'].cursor()
    cursor.execute(sql1, ())
    cursor.execute(sql2, ())
    transaction.commit_unless_managed()
    return cursor.rowcount


my_resource = MyModelResource()

urlpatterns = patterns('',
    (r'^api/', include(my_resource.urls)),
)



