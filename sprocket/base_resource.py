import inspect
import threading
import traceback

from django.conf.urls.defaults import *
from django.http import HttpResponse, HttpRequest
from django.utils import simplejson as json
from django.views.decorators.csrf import csrf_exempt

from .utils import MagicEnum, Val, magic_enum_meta_cls
from .auth import DefaultAuthentication
from .fields import ApiField

_current = threading.local()

class ResourceMeta(object):
    resource_name = None
    model_class = object
    included = []
    excluded = []


class BaseApiResource(object):
    _meta = ResourceMeta() # Overwritten by the __new__ method, but kept here so pylint can do type inference

    class Meta(ResourceMeta):
        resource_name = 'base-api-resource'
        authentication = DefaultAuthentication()

    def __new__(typ, *args, **kwargs):
        obj = object.__new__(typ, *args, **kwargs)        
        obj._meta = obj.Meta()
        return obj

    def __init__(self, *args, **kwargs):
        self._event_handlers = {}
        self._merge_in_mixins()
        self._fields = self._init_fields()
        self.urls = self._build_urls()

 

    # Initialize endpoints and mixins
    def _merge_in_mixins(self):
        '''
        All the methods in mixins that do not being with 'on_' or '_' get mixed into the API
        class - however we have to do some trickery so that when they are called 'self' is the
        'self' of the mixin, not of the API Resource.
        '''
        self.mixins = self.get_mixins() 
        for mixin in self.mixins:
            mixin.api = self
            for attr_name in dir(mixin):
                if not isinstance(attr_name, basestring):
                    continue
                if attr_name.startswith('on_'):
                    continue
                if attr_name == 'get_endpoints':
                    continue
                if attr_name.startswith('_'):
                    continue
                attr = getattr(mixin, attr_name)
                if inspect.ismethod(attr):
                    wrapped_method = self._wrap_mixin_method(attr)
                    setattr(self, attr_name, wrapped_method)


    def _wrap_mixin_method(self, attr, *args, **kwargs):
        def func(*args, **kwargs):
            return attr(*args, **kwargs)
        return func

    def get_mixins(self):
        # Override in subclasses
        return []


    def _build_urls(self):
        urls = []
        for endpoint in self._get_all_endpoints():
            urls.append(url(
                endpoint.url_pattern,
                self.wrap(endpoint), 
                name=endpoint.name))
        return urls   

    def _get_all_endpoints(self):
        endpoints = []
        endpoints.extend(self.get_override_endpoints())
        for mixin in self.mixins:
            endpoints.extend(mixin.get_endpoints())
        endpoints.extend(self.get_endpoints())

        return endpoints

    def get_endpoints(self):
        # Override me in a subclass, return a list of Endpoint objects
        raise NotImplementedError()

    def get_override_endpoints(self):
        # Override in a subclass - these endpoints have precedence over any mixin endpoints
        return []



    # Dispatching a request

    def wrap(self, endpoint):
        @csrf_exempt
        def handler(request, **kwargs):
            try:
                _current.request = request
                request.endpoint = endpoint
                return self._dispatch(endpoint, request, kwargs)
            except UserError, ex:
                return self.handle_user_error(request, endpoint, ex, ex.to_response())
            except ApiError, ex:
                traceback.print_exc()
                return self.handle_server_error(request, endpoint, ex, ex.to_response())
            except Exception, ex:
                traceback.print_exc()
                return self.handle_server_error(
                    request, 
                    endpoint, 
                    ex, 
                    HttpResponse(
                        json.dumps({'message': 'There was an internal error'}),
                        status=500
                    ))
            finally:
                _current.request = None
        return handler

    def _dispatch(self, endpoint, request, kwargs):
        self._authenticate(request)
        if not request.method in endpoint.http_method_to_api_method:
            return HttpResponse(status=405)
        method = getattr(self, endpoint.http_method_to_api_method.get(request.method))
        self._adjust_kwargs(endpoint, request, kwargs)
        result = method(**kwargs)
        response = self._result_to_response(result)
        self.execute_handlers(BaseEvents.process_response, response)
        return response

    def _authenticate(self, request):
        self.execute_handlers(BaseEvents.authenticate, request)

    def _adjust_kwargs(self, endpoint, request, kwargs):
        if 'resource_name' in kwargs:
            del kwargs['resource_name']
        data = None
        if request.raw_post_data:
            try:
                data = json.loads(request.raw_post_data)
            except Exception:
                raise UserError("Invalid syntax for the json data", status_code=400)

        self.execute_handlers(BaseEvents.adjust_kwargs_for_request, request, kwargs, data)

        for filter in endpoint.kwargs_filters:
            filter(self, request, kwargs, data)

    def _result_to_response(self, result):
        response = self.current_request.endpoint.to_response_func(result)
        if response:
            return response
        if isinstance(result, HttpResponse):
            return result
        elif isinstance(result, basestring):
            return HttpResponse(result)
        elif isinstance(result, dict):
            return HttpResponse(json.dumps(result))
        elif isinstance(result, list) and len(result) > 0 and isinstance(result[0], self._meta.model_class):
            return HttpResponse(self.obj_list_to_str(result))
        elif isinstance(result, list):
            return HttpResponse(json.dumps(result))
        elif isinstance(result, self._meta.model_class):
            return HttpResponse(self.obj_to_str(result))
        elif result == None and self.current_request.method == 'GET':
            return HttpResponse('{"message": "Object not found"}', status=404)
        elif result == True:
            return HttpResponse('{"message": "Action succeeded"}', status=200)
        else:
            raise Exception("Response was of an unexpected type")

    def handle_user_error(self, request, endpoint, exc, response):
        ''' Override this to add any custom error reporting logic '''
        return response

    def handle_server_error(self, request, endpoint, exc, response):
        ''' Override this to add any custom error reporting logic '''
        return response

    def execute_handlers(self, event_name, *args):
        for handler in self._get_handlers(event_name):
            handler(*args)

    def execute_filters(self, event_name, items, *args):
        for handler in self._get_handlers(event_name):
            items = handler(items, *args)
        return items

    def _get_handlers(self, event_name):
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = self._build_handlers_list(event_name)
        return self._event_handlers[event_name]

    def _build_handlers_list(self, event_name):
        handlers = []
        for mixin in self.mixins:
            handler = mixin.get_handler_for_event(event_name)
            if handler:
                handlers.append(handler)
        handler = getattr(self, 'on_' + event_name, None)
        if handler:
            handlers.append(handler)
        return handlers

    # Fields and Serialization
    def _init_fields(self):
        fields = []
        self.execute_handlers(BaseEvents.init_fields, fields)
        return fields

    def obj_to_str(self, obj):
        data = self.obj_to_dict(obj)
        return self.serialize(data)

    def serialize(self, data):
        return json.dumps(data)
    
    def obj_to_dict(self, obj):
        included = self._meta.included
        excluded = self._meta.excluded
        data = {}
        for field in self._fields:
            if field.name in excluded:
                continue
            if included and field.name not in included:
                continue
            field.obj_to_dict(obj, data)
        self.execute_handlers(BaseEvents.obj_to_dict, obj, data)
        return data

    def str_to_obj(self, post_data_byte_str):
        data = self.deserialize(post_data_byte_str)
        return self.dict_to_obj(data)

    def deserialize(self, data_str):
        try:
            return json.loads(data_str)
        except ValueError, e:
            raise UserError(e.message, status_code=400)

    def dict_to_obj(self, data):
        included = self._meta.included
        excluded = self._meta.excluded
        data = {}
        obj = self._meta.model_class()
        for field in self._fields:
            if field.name in excluded:
                continue
            if included and field.name not in included:
                continue
            field.dict_to_obj(data, obj)
        self.execute_handlers(BaseEvents.dict_to_obj, data, obj)
        return data
        

    def obj_list_to_str(self, objects):
        return json.dumps(self.obj_list_to_dicts(objects))

    def obj_list_to_dicts(self, objects):
        l = []
        for obj in objects:
            l.append(self.obj_to_dict(obj))
        return l

    # Helpers - we store the request object in thread local so we don't pass it around everywhere

    @property
    def current_request(self):
        req = _current.request
        if not req:
            req = EmptyRequest()
        return req

    @property
    def current_user(self):
        return self.current_request.user

    @property
    def current_username(self):
        user = self.current_user
        if user == None or not user.username:
            return ''
        else:
            return user.username

    # Default event handlers, to be overridden in subclasses
    def on_authenticate(self, request):
        if not request.user.is_authenticated():
            raise UnauthenticatedError("This is not an authenticated request")

class EmptyRequest(HttpRequest):
    def __nonzero__(self):
        return False


class RequestKwargFilters(object):
    '''
    Filters that take the incoming request data and generate 
    the appropriate keyword arguments that will be passed to the api method
    '''

    @staticmethod
    def from_json(api, request, kwargs, data):
        if request.method in ('POST', 'PUT') and request.raw_post_data:
            if not isinstance(data, dict):
                raise UserError("Missing or invalid json post data", status_code=400)
            kwargs.update(data)

    @staticmethod
    def from_keys(keys):
        def filter_func(api, request, kwargs, data):
            if not isinstance(data, dict):
                raise UserError("Missing or invalid json post data", status_code=400)
            for key in keys:
                if key not in data:
                    raise UserError("Expected key %s in the posted json data" % key)
                kwargs[key] = data[key]
        return filter_func

    @staticmethod
    def from_get_params(api, request, kwargs, data):
        if request.method != 'GET':
            return
        for field in api._fields:
            if field.name in request.GET:
                kwargs[field.name] = request.GET[field.name]

    @staticmethod
    def with_data(api, request, kwargs, data):
        if data == None:
            raise UserError("Missing or invalid json post data", status_code=400)
        kwargs['data'] = data


class EndPoint(object):
    def __init__(
        self, 
        url_pattern, 
        GET=None,
        DELETE=None,
        POST=None,
        PUT=None,
        name='',
        kwargs_filters=(),
        to_response_func=None):
        self.url_pattern = url_pattern
        self.http_method_to_api_method = {
            'GET': GET,
            'DELETE': DELETE,
            'POST': POST,
            'PUT': PUT
            }
        self.kwargs_filters = kwargs_filters
        self.name = name
        self.to_response_func = to_response_func
        if self.to_response_func == None:
            self.to_response_func = lambda o: None

class BaseEvents(object):
    __metaclass__ = magic_enum_meta_cls

    authenticate = Val()
    adjust_kwargs_for_request = Val()
    process_response = Val()
    dict_to_obj = Val()
    obj_to_dict = Val()
    init_fields = Val()

class ApiError(Exception):
    def __init__(self, message, status_code):
        super(ApiError, self).__init__(message)
        self.message = message
        self.status_code = status_code

    def to_response(self):
        return HttpResponse(json.dumps({'message': self.message}, status=self.status_code))

class UserError(ApiError):
    pass

class UnauthenticatedError(UserError):
    def __init__(self, message, status_code=403):
        super(UnauthenticatedError, self).__init__(message, status_code)


        
