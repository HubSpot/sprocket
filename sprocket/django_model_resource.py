
from .base_resource import EndPoint, UserError, ArgFilters, GET, PUT, DELETE, POST, BaseApiResource
from .utils import Val, magic_enum_meta_cls
from .fields import DateTimeField, ApiField, SimpleForeignKeyField, CharField, IntegerField, TextField
from django.db import models


django_field_to_sprocket_field = {
    models.DateTimeField.__name__: DateTimeField,
    models.ForeignKey.__name__: SimpleForeignKeyField,
    models.CharField.__name__: CharField,
    models.TextField.__name__: TextField,
    models.IntegerField.__name__: IntegerField,
    models.BigIntegerField.__name__: IntegerField,
    models.PositiveIntegerField.__name__: IntegerField,
}


class DjangoModelResource(BaseApiResource):

    def get_endpoints(self):
        endpoints = []
        endpoints += [
            EndPoint(
                r"^(?P<resource_name>%s)/$" % self._meta.resource_name,
                GET('paged_list', ArgFilters.all_from_query),
                POST('create', ArgFilters.all_from_json),
                ),
            EndPoint(
                r"^(?P<resource_name>%s)/(?P<pk>[0-9a-zA-Z\-_]+)/$" % self._meta.resource_name,
                GET('get', ArgFilters.all_from_query),
                PUT('update', ArgFilters.all_from_json),
                DELETE('delete'),
                ),
        ]
        return endpoints

    def on_init_fields(self, fields):
        for field in self._meta.model_class._meta.fields:
            cls = django_field_to_sprocket_field.get(field.__class__.__name__, ApiField)
            api_field = cls(field.name)
            fields.append(api_field)

    def create(self, **kwargs):
        obj = self.dict_to_obj(kwargs)
        return self.create_object(obj)

    def create_object(self, obj):
        self.execute_handlers(ModelEvents.pre_save_prepare, obj)
        self.execute_handlers(ModelEvents.pre_create_prepare, obj)

        self.execute_handlers(ModelEvents.pre_save_validate, obj)
        self.execute_handlers(ModelEvents.pre_create_validate, obj)

        self.execute_handlers(ModelEvents.pre_process_save, obj)
        self.execute_handlers(ModelEvents.pre_process_update, obj)

        obj.save()

        self.execute_handlers(ModelEvents.post_save, obj)
        self.execute_handlers(ModelEvents.post_create, obj)

        return obj

    def update_object(self, obj):
        data = self.obj_to_dict(obj)
        return self.update(obj.pk, **data)

    def update(self, pk, **kwargs):
        obj = self.get(pk=pk)
        if obj == None:
            return self.handle_update_not_found(pk, **kwargs)
        previous_data = {}
        for name in kwargs.keys():
            previous_data[name] = getattr(obj, name, None)
        obj = self.dict_to_obj(kwargs, obj)

        self.execute_handlers(ModelEvents.pre_save_prepare, obj)
        self.execute_handlers(ModelEvents.pre_update_prepare, obj, previous_data)

        self.execute_handlers(ModelEvents.pre_save_validate, obj)
        self.execute_handlers(ModelEvents.pre_update_validate, obj, previous_data)

        self.execute_handlers(ModelEvents.pre_process_save, obj)
        self.execute_handlers(ModelEvents.pre_process_update, obj, previous_data)

        obj.save()

        self.execute_handlers(ModelEvents.post_save, obj)
        self.execute_handlers(ModelEvents.post_update, obj, previous_data)

        return obj

    def handle_update_not_found(self, pk, **kwargs):
        raise UserError("Object not found for key %s" % pk, 404)

    def delete(self, pk):
        obj = self.get(pk=pk)
        if not obj:
            raise UserError("Object with key %s was not found, could not delete." % pk, 404)
        self.execute_handlers(ModelEvents.delete_prepare, obj)
        self.execute_handlers(ModelEvents.delete_validate, obj)
        self.execute_handlers(ModelEvents.delete_process, obj)
        obj.delete()
        self.execute_handlers(ModelEvents.post_delete, obj)
        return True

    def get(self, **kwargs):
        items = self._list_and_count(limit=1, _include_total=False, **kwargs)
        if items:
            self.execute_handlers(ModelEvents.get_object, items[0])
            return items[0]
        else:
            return None

    def paged_list(self, offset=0, limit=20, **kwargs):
        items, total = self._list_and_count(offset=int(offset), limit=int(limit), **kwargs)
        data = {
            'offset': int(offset),
            'limit': int(limit),
            'total_count': total,
            'objects': self.obj_list_to_dicts(items)
            }
        return data

    def list(self, **kwargs):
        return self._list_and_count(_include_total=False, **kwargs)

    def _list_and_count(self, offset=0, limit=None, _include_total=True, **kwargs):
        q_filters, filters = build_django_orm_filters_from_params(self, kwargs)
        self.execute_handlers(ModelEvents.adjust_orm_filters, q_filters, filters)
        queryset = self._meta.model_class.objects.filter(*q_filters, **filters)
        queryset = self.execute_filters(ModelEvents.chain_queryset, queryset)
        if limit != None:
            items = queryset[offset:offset + limit]
        else:
            items = list(queryset)
        items = self.execute_filters(ModelEvents.filter_objects, items)
        items = list(items)
        self.execute_handlers(ModelEvents.list_objects, items)
        if _include_total:
            return items, queryset.count()
        return items


def build_django_orm_filters_from_params(api_resource, params):
    '''
    Takes filters that came in from a query string and turns them into
    django ORM filters
    '''
    q_filters = []
    dj_filters = {}
    for key, value in params.items():
        parts = key.split('__')
        field_name = parts.pop(0)
        if field_name not in api_resource.field_by_name and not field_name == 'pk':
            continue
        filter_type = 'exact'
        if parts:
            filter_type = parts[-1]
        validate_filter(api_resource, field_name, filter_type)

        if value in [True, 'true', 'True']:
            value = True
        elif value in [False, 'false', 'False']:
            value = False
        elif value in (None, 'nil', 'none', 'None'):
            value = None

        if filter_type == 'ne':
            q_filters.append(
                ~models.Q(**{field_name: value})
            )
            continue

        filter_key = field_name + '__' + filter_type

        is_container = type(value) in (list, set, frozenset, tuple)
        # if we're doing an "in" query, all queries need to be in an iterable container, even if one variable.
        if filter_type in ["in", "range"]:
            if not is_container:
                value = [value]
        else:
            if is_container:
                if len(value) > 0:
                    value = value[0]
                else:
                    value = None

        # Hack to fix filtering of foreign keys, which need to be filtered
        # on the field without the _id part addded
        if isinstance(api_resource.field_by_name.get(field_name), SimpleForeignKeyField):
            if field_name.endswith('_id') and filter_type == 'exact':
                filter_key = field_name[:-3] + '__exact'

        dj_filters[filter_key] = value

    return q_filters, dj_filters


def validate_filter(api, field_name, filter_type):
    if not field_name in api._meta.filtering:
        raise UserError('You cannot filter on the field %s ' % field_name, status_code=400)
    if not filter_type in api._meta.filtering.get(field_name, []):
        raise UserError('You cannot filter on the field %s in the form of %s ' % (field_name, filter_type), 400)


class ModelEvents(object):
    __metaclass__ = magic_enum_meta_cls

    pre_save_prepare = Val()
    pre_save_validate = Val()
    pre_process_save = Val()
    post_save = Val()

    pre_create_prepare = Val()
    pre_create_validate = Val()
    pre_process_create = Val()
    post_create = Val()

    pre_update_prepare = Val()
    pre_update_validate = Val()
    pre_process_update = Val()
    post_update = Val()

    adjust_orm_filters = Val()
    chain_queryset = Val()
    filter_objects = Val()
    list_objects = Val()
    get_object = Val()

    delete_prepare = Val()
    delete_validate = Val()
    delete_process = Val()
    post_delete = Val()
