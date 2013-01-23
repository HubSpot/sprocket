Sprocket

A better RESTful API framework for Python and Django.

Sprocket makes it easy to expose normal python functions in a web API through a restful interface. It works out of the box with Django models and provides a mixin and events system for easily adding in reusable, self-contained components into API.

Core Ideas

When using Sprocket, you will define Resource classes containing normal Python methods which perform the tasks of your API. For example, a Message resource may contain a send() method.

To expose these methods in an API, you will add EndPoints to your Resource class. An EndPoint contains a URL, a method to call, and any validation on the input from the request.

Resource classes are configured by defining inner Meta classes. Some of this configuration includes the “resource name”, which is reused throughout the Resource’s URLs.

To define reusable behavior which can appear in multiple Resources, you may create Mixin classes. Just like Resources, Mixin classes may define additional EndPoints.

Finally, you may communicate between Mixins and resources with Events. Defining event handlers allows you to customize behavior flexibly.
BaseApiResource

Serialization/Deserialization


obj_to_str(obj)
obj <= instance of the resource’s model_class

Returns a string representation of the object

serialize(data)
data <= dictionary

Returns a JSON string representation of the given dictionary.

obj_to_dict(obj)
obj <= instance of the resource’s model_class

+triggers: BaseEvents.obj_to_dict
Returns a dictionary representation of the object, with each of the resources _fields_ stored in a key. It respects any _includes_ or _excludes_ lists you define in the Meta object.

str_to_obj(post_data_byte_str)
post_data_byte_str <= string to convert

Deserializes the post_data_byte_str and returns an instance of the resource’s model_class.

dict_to_obj(data, obj=None)
data <= dictionary
obj <= instance of the resource’s model_class
+triggers: BaseEvents.dict_to_obj

Assigns each value in data to the obj, if given, or a new instance of the resource’s model_class.

obj_list_to_str(objects)
objects <= list of instances of the resource’s model_class

Serializes the list of objects into a JSON-encoded list. For example, the python list:
[<emptyObj>, <emptyObj>] would return “[{}, {}]”.

obj_list_to_dicts(objects)
objects <= list of instances of resource’s model_class

Returns a list of dictionary representations of the objects, converted using obj_to_dict().
Helpers

These are tracked using the currently-running thread.

current_request

current_user

current_username

current_response_status_code

set_current_status_code(status_code)
status_code <= int

set_response_header(name, header)
name <= string
header <= string

set_response_cookie(*args, **kwargs)

on_authenticate(request)
Checks if user is authenticated. Should be overridden in subclasses.
ResourceMeta

BaseApiResource expects an internally-defined class called Meta, which should be a subclass of ResourceMeta. ResourceMeta subclasses may define the following class attributes:

resource_name
A string used to identify the resource in urls. For example, a “BlogPost” Resource might have the name “blog-post” and appear in URLs such as /blog-post/31.

authentication
A helper object which defines the authentication method used to access this resource.

model_class
A Django Model class. Required when using DjangoModelResource.

ArgFilters

ArgFilters make it easy to retrieve input parameters during an API call. They are passed into EndPointMethod constructors.

all_from_json
Target method receives the entire JSON dictionary, as converted into a kwargs dictionary. Considers an absence of a valid JSON string an exception.

all_from_json_custom(allow_empty=False)
allow_empty <= boolean
Identical to all_from_json, but if allow_empty is True, then no error is raised if the request contains no JSON at all.

fields_from_json
Target method receives one keyword argument for each of the fields defined in the resource’s ResourceMeta, if the request contains a value for that field.

from_keys(keys)
keys <= list of strings
Target method receives one keyword argument for each of the strings in _keys_. Requests missing one or more key raise a UserError.

keys_from_query(keys, all_required=True)
keys <= list of strings
all_required <= boolean
Target method receives one keyword for each key/value in the request’s querystring. If all_required is set to true, any _keys_ not present in the qstring will return an error.

all_from_query
Target method receives one keyword and value for each key/value in the request’s querystring.

with_data
Identical to all_from_json

Typecasting Argfilters

These can be chained after a data-fetching Argfilter to typecast values.

convert_to_bool_values(param_names=None)
param_names <= list of strings
Params given are converted to boolean values in place before continuing on to the target method.

convert_to_int_values(param_names=None)
param_names <= list of strings
Params given are converted to integer values in place before continuing on to the target method.

convert(**kwargs)
kwargs <= key/values, where values are all callables.
If a key in the kwargs matches one in the input, the input value is passed through the value.
For example:
Argfilters.convert(user_id=lambda x: int(x) + 10)
input:
{“user_id”: 32, “foo”: “bar”}
output:
{“user_id”: 42, “foo”: “bar”}

Adding Endpoints

EndPoints describe a URL-to-method mapping, with additional validation parameters.

class EndPoint(url_pattern, *end_point_methods, **kwargs)
url_pattern <= regex, including capture groups for additional parameters which should be passed on to the target method
end_point_methods <= any additional positional arguments after url_pattern indicate EndPointMethods associate with that EndPoint

Examples:

EndPoint(
    r"^%s/changes$" % self._meta.resource_name,
    GET(“get_changes”)
)

class EndPointMethod(api_method_name, arg_filters)
api_method_name <= string, must match method name defined for resource
arg_filters <= iterable containing zero or more ArgFilters

This is a base class which describes a mapping between an HTTP Method and a Python method defined for your resource, with ArgFilters providing validation on the arguments.

class PUT
class POST
class GET
class DELETE

class ApiError(message, status_code, error_dict, errors)
message <= string with a message for the API user
status_code <= integer with an HTTP error code
error_dict <= dictionary with multiple messages for the user
error <= list of strings, messages for the user

Raise an ApiError exception to let Sprocket handle rendering an error response for you.

UserError
Subclass of ApiError to designate error caused by users’ mistakes.
DjangoModelResource

A subclass of BaseApiResource which defines EndPoints for basic CRUD operations using Django’s ORM.
