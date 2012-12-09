import inspect
import threading
import traceback

from django.conf.urls.defaults import *
from django.http import HttpResponse, HttpRequest, HttpResponseNotAllowed
from django.utils import simplejson as json
from django.views.decorators.csrf import csrf_exempt

from .utils import MagicEnum, Val, magic_enum_meta_cls
from .auth import DefaultAuthentication
from .fields import ApiField


class ResourceMeta(object):
    resource_name = None
    model_class = object
    includes = []
    excludes = []
    filtering = None

    def __init__(self):
        if not self.filtering:
            self.filtering = {}
        if not 'id' in self.filtering:
            self.filtering['id'] = ['exact']
        if not 'pk' in self.filtering:
            self.filtering['pk'] = ['exact']


class BaseApiResource(object):
    _meta = ResourceMeta()  # Overwritten by the __new__ method, but kept here so pylint can do type inference

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
        self.fields = self._init_fields()
        self.field_names = [field.name for field in self.fields]
        self.field_by_name = dict([(field.name, field) for field in self.fields])
        self.urls = self._build_urls()

    # Initialize endpoints and mixins
    def _merge_in_mixins(self):
        '''
        All the methods in mixins that do not being with 'on_' or '_' get mixed into the API
        class - however we have to do some trickery so that when they are called 'self' is the
        'self' of the mixin, not of the API Resource.
        '''
        self.mixins = self.get_mixins()
        self.mixins_by_name = {}
        for mixin in self.mixins:
            mixin.api = self
            self.mixins_by_name[mixin.__class__.__name__] = mixin
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
                _thread_local.current = CurrentRequestThreadHolder(request)
                request.endpoint = endpoint
                return self._dispatch(endpoint, request, kwargs)
            except UserError, ex:
                return self.handle_user_error(request, endpoint, ex, ex.to_response())
            except ApiError, ex:
                return self.handle_server_error(request, endpoint, ex, ex.to_response())
            except Exception, ex:
                return self.handle_server_error(
                    request,
                    endpoint,
                    ex,
                    HttpResponse(
                        json.dumps({'message': 'There was an internal error'}),
                        status=500
                    ))
            finally:
                _thread_local.current = None
        return handler

    def _dispatch(self, endpoint, request, kwargs):
        self._authenticate(request)
        if not request.method in endpoint.http_method_dict:
            return HttpResponseNotAllowed(endpoint.http_method_dict.keys())
        method_endpoint = request.method_endpoint = endpoint.http_method_dict[request.method]
        if isinstance(method_endpoint.api_method_name, basestring):
            method = getattr(self, method_endpoint.api_method_name)
        else:
            method = method_endpoint.api_method_name
        self._adjust_kwargs(method_endpoint, request, kwargs)
        self.execute_handlers(BaseEvents.pre_dispatch_request, request, kwargs)
        result = method(**kwargs)
        response = self._result_to_response(result)
        self.add_preset_response_info(response)
        self.execute_handlers(BaseEvents.process_response, response)
        return response

    def _authenticate(self, request):
        self.execute_handlers(BaseEvents.authenticate, request)

    def _adjust_kwargs(self, method_endpoint, request, kwargs):
        if 'resource_name' in kwargs:
            del kwargs['resource_name']
        if 'api_name' in kwargs:
            del kwargs['api_name']

        self.execute_handlers(BaseEvents.adjust_kwargs_for_request, request, kwargs)

        for filter in method_endpoint.arg_filters:
            filter(self, request, kwargs)

    def _result_to_response(self, result):
        response = self.current_request.method_endpoint.to_response_func(result)
        if response:
            return response
        if isinstance(result, HttpResponse):
            return result
        status_code = 200
        if self.current_response_status_code != None:
            status_code = self.current_response_status_code
        if isinstance(result, basestring):
            return HttpResponse(result, status=status_code)
        elif isinstance(result, dict):
            return HttpResponse(json.dumps(result), status=status_code)
        elif isinstance(result, list) and len(result) > 0 and isinstance(result[0], self._meta.model_class):
            return HttpResponse(self.obj_list_to_str(result), status=status_code)
        elif isinstance(result, list):
            return HttpResponse(json.dumps(result), status=status_code)
        elif isinstance(result, self._meta.model_class):
            return HttpResponse(self.obj_to_str(result), status=status_code)
        elif result == None and self.current_request.method == 'GET':
            return HttpResponse('{"message": "Object not found"}', status=404)
        elif result == True:
            return HttpResponse('{"succeeded": true, "message": "Action succeeded"}', status=status_code)
        else:
            raise Exception("Response was of an unexpected type")

    def add_preset_response_info(self, response):
        '''
        Adds any headers or cookies that were set during the processing of the api call
        '''
        for key, val in _thread_local.current.response_headers.items():
            response[key] = val
        for args, kwargs in _thread_local.current.cookie_setters:
            response.set_cookie(*args, **kwargs)
        if 'content-type' not in _thread_local.current.response_headers:
            response['Content-type'] = 'application/json'

    def handle_user_error(self, request, endpoint, exc, response):
        ''' Override this to add any custom error reporting logic '''
        return response

    def handle_server_error(self, request, endpoint, exc, response):
        ''' Override this to add any custom error reporting logic '''
        traceback.print_exc()
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
        includes = self._meta.includes
        excludes = self._meta.excludes
        data = {}
        for field in self.fields:
            if field.name in excludes:
                continue
            if includes and field.name not in includes:
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

    def dict_to_obj(self, data, obj=None):
        includes = self._meta.includes
        excludes = self._meta.excludes
        if obj == None:
            obj = self._meta.model_class()
        for field in self.fields:
            if field.name in excludes:
                continue
            if includes and field.name not in includes:
                continue
            field.dict_to_obj(data, obj)
        self.execute_handlers(BaseEvents.dict_to_obj, data, obj)
        return obj

    def obj_list_to_str(self, objects):
        return json.dumps(self.obj_list_to_dicts(objects))

    def obj_list_to_dicts(self, objects):
        return [self.obj_to_dict(obj) for obj in objects]

    # Helpers - we store the request object in thread local so we don't pass it around everywhere

    @property
    def current_request(self):
        req = self.thread_current.request
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

    @property
    def current_response_status_code(self):
        return self.thread_current.status_code

    def set_current_status_code(self, status_code):
        self.thread_current.status_code = status_code

    def set_response_header(self, name, value):
        self.thread_current.response_headers[name.lower()] = value

    def set_response_cookie(self, *args, **kwargs):
        self.thread_current.cookie_setters.append((args, kwargs))

    @property
    def thread_current(self):
        c = getattr(_thread_local, 'current', None)
        if c == None:
            c = CurrentRequestThreadHolder(None)
        return c

    # Default event handlers, to be overridden in subclasses
    def on_authenticate(self, request):
        if not request.user.is_authenticated():
            raise UnauthenticatedError("This is not an authenticated request")


class EmptyRequest(HttpRequest):
    def __nonzero__(self):
        return False


class ArgFilters(object):
    '''
    Filters that take the incoming request data and generate
    the appropriate keyword arguments that will be passed to the api method
    '''

    @staticmethod
    def all_from_json(api, request, kwargs):
        return ArgFilters.all_from_json_custom()(api, request, kwargs)

    @staticmethod
    def all_from_json_custom(allow_empty=False):
        def filter_func(api, request, kwargs):
            if request.method in ('POST', 'PUT'):
                data = ArgFilters.get_json_data(request, allow_empty)
                if data:
                    kwargs.update(data)
        return filter_func

    @staticmethod
    def fields_from_json(api, request, kwargs):
        if request.method in ('POST', 'PUT'):
            data = ArgFilters.get_json_data(request)
            for field in api.fields:
                if field.name in data:
                    kwargs[field.name] = data[field.name]

    @staticmethod
    def from_keys(keys):
        if not hasattr(keys, '__iter__'):
            keys = [keys]

        def filter_func(api, request, kwargs):
            data = ArgFilters.get_json_data(request)
            for key in keys:
                if key not in data:
                    raise UserError("Expected key %s in the posted json data" % key, 400)
                kwargs[key] = data[key]

        return filter_func

    @staticmethod
    def keys_from_query(keys, all_required=True):
        def filter_func(api, request, kwargs):
            for key in keys:
                if key not in request.GET:
                    if all_required:
                        raise UserError("Expected key %s in the posted json data" % key)
                else:
                    values = request.GET.getlist(key)
                    if len(values) > 1:
                        kwargs[key] = values
                    elif len(values) == 1:
                        kwargs[key] = values[0]
        return filter_func

    @staticmethod
    def fields_from_query_plus(additional_keys):
        def filter_func(api, request, kwargs):
            return ArgFilters.fields_from_query(api, request, kwargs, additional_keys=additional_keys)
        return filter_func

    @staticmethod
    def fields_from_query(api, request, kwargs, additional_keys=('offset', 'limit', 'order_by')):
        field_names = set([field.name for field in api.fields])
        for name, values in request.GET.lists():
            if name in field_names or name in additional_keys:
                if len(values) > 1:
                    kwargs[name] = values
                elif len(values) == 1:
                    kwargs[name] = values[0]
                continue
            # We also allow queries in the form 'field_name__gt', 'field_name__lt' that get passed into filters
            i = name.find('__')
            if i > -1:
                if name[:i] in field_names:
                    if len(values) > 1:
                        kwargs[name] = values
                    elif len(values) == 1:
                        kwargs[name] = values[0]

    _internal_query_keys = ['portalId', 'hapikey', 'scopes']

    @staticmethod
    def all_from_query(api, request, kwargs):
        for name, values in request.GET.lists():
            if name not in ArgFilters._internal_query_keys:
                if len(values) > 1:
                    kwargs[name] = values
                elif len(values) == 1:
                    kwargs[name] = values[0]

    @staticmethod
    def with_data(api, request, kwargs):
        try:
            data = json.loads(request.raw_post_data)
        except Exception:
            raise UserError("Invalid syntax for the json data", status_code=400)
        kwargs['data'] = data

    @staticmethod
    def get_json_data(request, allow_empty=False):
        post_data = request.raw_post_data
        if allow_empty and \
           (post_data is None or len(post_data) == 0 or post_data == ''):
            return None
        try:
            data = json.loads(post_data)
        except Exception:
            raise UserError("Invalid syntax for the json data", status_code=400)
        return data

    @staticmethod
    def convert_to_bool_values(param_names=None):
        '''
        Returns a filter function to parse parameters (all or just the given ones) as specific types
        @param_names - (optional) - string names of boolean-valued params
        '''
        def filter_func(api, request, kwargs):
            for key, val in kwargs.items():
                if param_names == None or (param_names and key in param_names):
                    if val == 'true':
                        kwargs[key] = True
                    elif val == 'false':
                        kwargs[key] = False

        return filter_func

    @staticmethod
    def convert_to_int_values(param_names=None):
        '''
        Returns a filter function to parse parameters (all or just the given ones) as integer values
        @param_names - (optional) - string names of integer-valued params
        '''
        def filter_func(api, request, kwargs):
            for key, val in kwargs.items():
                # Ensure object is a string before trying to determine if its content is of integer value
                if val and hasattr(val, 'isdigit') and val.isdigit() and \
                   (param_names == None or (param_names and key in param_names)):
                    try:
                        kwargs[key] = int(val)
                    except:
                        pass
        return filter_func

    @staticmethod
    def convert(**keys_to_callable):
        '''
        k1=fn1,
        k2=fn2,
        ...
        '''
        def filter_func(api, request, kwargs):
            for key, val in kwargs.items():
                # Ensure object is a string before trying to determine if its content is of integer value
                if key not in keys_to_callable:
                    continue

                try:
                    kwargs[key] = keys_to_callable[key](val)
                except:
                    pass

        return filter_func


class EndPoint(object):
    def __init__(
        self,
        url_pattern,
        *end_point_methods,
        **kwargs):
        self.url_pattern = url_pattern
        self.http_method_dict = {}
        for epm in end_point_methods:
            self.http_method_dict[epm.__class__.__name__.upper()] = epm
        self.name = kwargs.get('name', '')


class EndPointMethod(object):
    '''
    Defines the endpoint handler for a particular HTTP Method
    '''
    def __init__(self, api_method_name, arg_filters=(), to_response_func=None):
        '''
        @api_method_name - a name a method that exists on the API resource that will be the handler for this endpoint
        @arg_filters - a list of filter functions that will pull keys and values of the request and include them as kwargs
        @to_response_func - optional if included will turn the result of the api_method into an HttpResponse object
        '''
        if callable(arg_filters):
            arg_filters = [arg_filters]
        if to_response_func == None:
            to_response_func = lambda o: None

        self.api_method_name = api_method_name
        self.to_response_func = to_response_func
        self.arg_filters = arg_filters


class PUT(EndPointMethod):
    pass


class POST(EndPointMethod):
    pass


class GET(EndPointMethod):
    pass


class DELETE(EndPointMethod):
    pass


class BaseEvents(object):
    __metaclass__ = magic_enum_meta_cls

    authenticate = Val()
    adjust_kwargs_for_request = Val()
    pre_dispatch_request = Val()
    process_response = Val()
    dict_to_obj = Val()
    obj_to_dict = Val()
    init_fields = Val()


class ApiError(Exception):
    def __init__(self, message, status_code, error_dict=None, errors=(), extra_data=None):
        super(ApiError, self).__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_dict = error_dict
        self.extra_data = extra_data
        self.errors = errors

    def get_data(self):
        d = {'message': self.message, 'succeeded': False}
        if self.error_dict != None:
            d['error_dict'] = self.error_dict
        if self.errors != None:
            d['errors'] = self.errors

        if self.extra_data != None:
            d.update(self.extra_data)
        return d

    def to_response(self):
        return HttpResponse(json.dumps(self.get_data()), status=self.status_code)


class UserError(ApiError):
    pass


class UnauthenticatedError(UserError):
    def __init__(self, message, status_code=403):
        super(UnauthenticatedError, self).__init__(message, status_code)


class CurrentRequestThreadHolder(object):
    def __init__(self, request):
        self.request = request
        self.response_headers = {}
        self.cookie_setters = []
        self.status_code = None

_thread_local = threading.local()
_thread_local.current = CurrentRequestThreadHolder(None)
