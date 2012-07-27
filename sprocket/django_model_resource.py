
from .base_resource import EndPoint, ApiField, BaseEvents, UserError, RequestKwargFilters, ResourceMeta

class DjangoModelResource(BaseApiResource):

    class Meta(object):
        pass

    def get_base_endpoints(self):
        endpoints = []
        endpoints += [
            EndPoint(
                r"^(?P<resource_name>%s)/$" % self._meta.resource_name,
                {'GET': 'list'},
                kwargs_filters=[
                    RequestKwargFilters.from_get_params
                    ]),
            EndPoint(
                r"^(?P<resource_name>%s)/(?P<pk>[0-9a-zA-Z\-_]+)/$" % self._meta.resource_name,
                {'GET': 'get',
                 'PUT': 'save',
                 'DELETE': 'delete'},
                kwargs_filters=[
                    RequestKwargFilters.from_get_params,
                    RequestKwargFilters.from_json
                    ]),
        ]
        return endpoints

    def on_init_fields(self, fields):
        for field in self._meta.model_class._meta.fields:
            api_field = ApiField(field.name)
            fields.append(api_field)

    def on_authenticate(self, request):
        if not request.user.is_authenticated():
            raise UnauthenticatedError("You do not have access to this resource")
        

    def model_response(self, result):
        if isinstance(result, self.model_class) and result != None:
            return HttpResponse(self.obj_to_json(result))
        elif isinstance(result, list) and len(result) > 0 and isinstance(result[0], self.model_class):
            obj_dicts = []
            for obj in result:
                obj_dicts.append(self.obj_to_dict(obj))
            return HttpResponse(json.dumps(obj_dicts))

    def create(self, **kwargs):
        obj = self._meta.object_class(**kwargs)
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
        obj = self.get(pk)
        previous_data = {}
        for name in kwargs.items():
            previous_data[name] = getattr(obj, name, None)
        
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
        obj = self.get(pk)

        self.execute_handlers(ModelEvents.prepare_delete, obj)
        self.execute_handlers(ModelEvents.validate_delete, obj)
        self.execute_handlers(ModelEvents.process_delete, obj)
        obj.delete()
        self.execute_handlers(ModelEvents.post_delete, obj)
        

    def get(self, **kwargs):
        items = self._list_and_count(limit=1, _include_total=False, **kwargs)
        if items:
            return items[0]
        else:
            return None

    def paged_list(self, offset=0, limit=20, **kwargs):
        items, total = self._list_and_count(**kwargs)
        data = {
            'offset': offset,
            'limit': limit,
            'total_count': total,
            'objects': self.obj_list_to_dicts(items)
            }

    def list(self, **kwargs):
        return _list_and_count(**kwargs, _include_total=False)

    def _list_and_count(self, offset=0, limit=None, _include_total=True, **kwargs):
        projects = ProjectDefinition.objects.filter(**kwargs)
        self.execute_handlers(ModelEvents.adjust_orm_filters, kwargs)
        queryset = self._meta.model_class.objects.filter(**kwargs)
        queryset = self.execute_filters(ModelEvents.chain_queryset, queryset)
        if limit != None:
            items = queryset[offset:offset+limit]
        else:
            items = list(queryset)
        items = self.execute_filters(ModelEvents.filter_items, items)
        items = list(items)
        if _include_totals:
            return items, queryset.count()
        return items



class ModelEvents(object):
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
