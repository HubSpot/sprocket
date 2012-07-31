
from .base_resource import EndPoint, ApiField, BaseEvents, UserError, ArgFilters, ResourceMeta, GET, PUT, DELETE, POST, BaseApiResource
from .utils import Val, magic_enum_meta_cls
from .fields import DateTimeField, ApiField
from django.db.models import Model, CharField, DateTimeField as DjDateTimeField, EmailField, IntegerField


django_field_to_sprocket_field = {
    DjDateTimeField.__name__: DateTimeField
}

class DjangoModelResource(BaseApiResource):

    class Meta(object):
        pass

    def get_endpoints(self):
        endpoints = []
        endpoints += [
            EndPoint(
                r"^(?P<resource_name>%s)/$" % self._meta.resource_name,
                GET('paged_list', ArgFilters.fields_from_query),
                POST('create', ArgFilters.fields_from_json),
                ),
            EndPoint(
                r"^(?P<resource_name>%s)/(?P<pk>[0-9a-zA-Z\-_]+)/$" % self._meta.resource_name,
                GET('get', ArgFilters.fields_from_query),
                PUT('update', ArgFilters.fields_from_json),
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
        obj = self._meta.model_class()
        for field in self._fields:
            if field.name in kwargs:
                field.dict_to_obj(kwargs, obj)
        return self.create_object(obj)

    def create_object(self, obj):
        self.execute_handlers(ModelEvents.prepare_create, obj)
        self.execute_handlers(ModelEvents.prepare_save, obj)

        self.execute_handlers(ModelEvents.validate_create, obj)
        self.execute_handlers(ModelEvents.validate_save, obj)

        self.execute_handlers(ModelEvents.process_save, obj)
        self.execute_handlers(ModelEvents.process_update, obj)

        obj.save()

        self.execute_handlers(ModelEvents.post_save, obj)
        self.execute_handlers(ModelEvents.post_update, obj)

        return obj

    def update_object(self, obj):
        data = self.obj_to_dict(obj)
        return self.update(obj.pk, **data)

    def update(self, pk, **kwargs):
        obj = self.get(pk=pk)
        previous_data = {}
        for name in kwargs.keys():
            previous_data[name] = getattr(obj, name, None)

        for field in self._fields:
            if field.name in kwargs:
                field.dict_to_obj(kwargs, obj)
        
        self.execute_handlers(ModelEvents.prepare_save, obj)
        self.execute_handlers(ModelEvents.prepare_update, obj, previous_data)


        self.execute_handlers(ModelEvents.validate_save, obj)
        self.execute_handlers(ModelEvents.validate_update, obj, previous_data)

        self.execute_handlers(ModelEvents.process_save, obj)
        self.execute_handlers(ModelEvents.process_update, obj, previous_data)

        obj.save()

        self.execute_handlers(ModelEvents.post_save, obj)
        self.execute_handlers(ModelEvents.post_update, obj, previous_data)

        return obj
        

    def delete(self, pk):
        obj = self.get(pk=pk)

        self.execute_handlers(ModelEvents.prepare_delete, obj)
        self.execute_handlers(ModelEvents.validate_delete, obj)
        self.execute_handlers(ModelEvents.process_delete, obj)
        obj.delete()
        self.execute_handlers(ModelEvents.post_delete, obj)
        return True

    def get(self, **kwargs):
        items = self._list_and_count(limit=1, _include_total=False, **kwargs)
        if items:
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
        self.execute_handlers(ModelEvents.adjust_orm_filters, kwargs)
        queryset = self._meta.model_class.objects.filter(**kwargs)
        queryset = self.execute_filters(ModelEvents.chain_queryset, queryset)
        if limit != None:
            items = queryset[offset:offset+limit]
        else:
            items = list(queryset)
        items = self.execute_filters(ModelEvents.filter_items, items)
        items = list(items)
        if _include_total:
            return items, queryset.count()
        return items



class ModelEvents(object):
    __metaclass__ = magic_enum_meta_cls
    prepare_create = Val()
    validate_create = Val()
    process_create = Val()
    post_create = Val()

    prepare_save = Val()
    validate_save = Val()
    process_save = Val()
    post_save = Val()

    prepare_update = Val()
    validate_update = Val()
    process_update = Val()
    post_update = Val()


    prepare_delete = Val()
    validate_delete = Val()
    process_delete = Val()
    post_delete = Val()
    
    adjust_orm_filters = Val()
    chain_queryset = Val()
    filter_items = Val()
