from datetime import datetime
import time
from unittest import TestCase

from django.conf import settings
from django.conf.urls.defaults import patterns, include
from django.db.models import Model, CharField, DateTimeField as DjDateTimeField, EmailField, IntegerField
from django.db import connections, transaction
from django.test.client import Client
from django.utils import simplejson

from mocking_bird.mocking import MockingBirdMixin

from ..django_model_resource import DjangoModelResource
from ..base_resource import ResourceMeta


class SimpleCase(TestCase, MockingBirdMixin):
    def test_direct_crud(self):
        label = 'MyLabelz'
        email = 'amail@maila.com'
        second_label = 'MySecondLabel'

        obj = my_resource.create(
            label=label,
            email=email,
            age=17)
        obj = my_resource.get(pk=obj.pk)
        self.assertEquals(label, obj.label)

        obj = my_resource.get(email=email)
        self.assertEquals(label, obj.label)

        second_label = 'MySecondLabel'
        obj = my_resource.create(
            label=second_label,
            age=21)

        objs = my_resource.list()
        self.assertEquals(2, len(objs))

        # test multiple __in
        objs = my_resource.list(age__in=[17, 21])
        self.assertEquals(2, len(objs))

        # test multiple __in with alternative container
        objs = my_resource.list(age__in=set([17, 21]))
        self.assertEquals(2, len(objs))

        # test single __in
        objs = my_resource.list(age__in=[17])
        self.assertEquals(1, len(objs))

        # test single equals
        objs = my_resource.list(age=17)
        self.assertEquals(1, len(objs))

        # test range
        objs = my_resource.list(age__range=[17, 21])
        self.assertEquals(2, len(objs))

        # test gt
        objs = my_resource.list(age__gt=17)
        self.assertEquals(1, len(objs))

        # test gte
        objs = my_resource.list(age__gte=17)
        self.assertEquals(2, len(objs))

        # test lt
        objs = my_resource.list(age__lt=21)
        self.assertEquals(1, len(objs))

        # test lte
        objs = my_resource.list(age__lte=21)
        self.assertEquals(2, len(objs))

    def test_http_crud(self):
        c = Client()

        new_label = 'NewMylabelszz'
        dt = datetime(2011, 7, 1, 12, 30, 0)
        dt_str = dt.strftime('%Y-%m-%d %H:%M:%S')

        post_data = {
            'label': 'MyLabelz',
            'published_at': dt_str,
            'age': 17,
            'email': "amail@maila.com"
            }

        second_post_data = {
            'label': 'MySecondLabel',
            'published_at': dt_str,
            'age': 21,
            'email': 'amail2@maila.com',
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
        self.assertTrue(post_data['label'], data['label'])
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
            data=simplejson.dumps(second_post_data),
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

        # check on filtering
        r = c.get('/api/my-resource/?age__in=17&age__in=21')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(2, len(data['objects']))
        self.assertEquals(2, data['total_count'])

        # check on filtering (single value)
        r = c.get('/api/my-resource/?age__in=17')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(1, len(data['objects']))
        self.assertEquals(1, data['total_count'])

        r = c.get('/api/my-resource/?age__gt=17')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(1, len(data['objects']))
        self.assertEquals(1, data['total_count'])

        r = c.get('/api/my-resource/?age__gte=17')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(2, len(data['objects']))
        self.assertEquals(2, data['total_count'])

        r = c.get('/api/my-resource/?age__lt=21')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(1, len(data['objects']))
        self.assertEquals(1, data['total_count'])

        r = c.get('/api/my-resource/?age__lte=21')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(2, len(data['objects']))
        self.assertEquals(2, data['total_count'])

        # check passing multiple vals to something expecting a single
        r = c.get('/api/my-resource/?age=17&age=21')
        data = simplejson.loads(r.content)
        self.assertEquals(200, r.status_code)
        self.assertEquals(1, len(data['objects']))
        self.assertEquals(1, data['total_count'])

        # Delete the object
        r = c.delete(
            '/api/my-resource/%s/' % obj_data['id'],
            content_type='application/json')
        self.assertEquals(200, r.status_code)

        r = c.get('/api/my-resource/%s/' % obj_data['id'])
        self.assertEquals(404, r.status_code)

    url_conf = 'sprocket.test.test_django_model_resource'

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
            self.pk = long(time.time() * 1000)
        super(FakeModel, self).save()

    class Meta:
        db_table = 'sprocket_test_fake_model'


class MyModelResource(DjangoModelResource):
    class Meta(ResourceMeta):
        resource_name = 'my-resource'
        model_class = FakeModel
        filtering = {
            'email': ['exact'],
            'age': ['exact', 'range', 'gt', 'gte', 'lt', 'lte', 'in'],
            }

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
