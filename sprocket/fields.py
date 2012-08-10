from datetime import datetime

class ApiField(object):
    def __init__(self, name, label=None, obj_attr_name=None, help_text='', default=None):
        self.name = name
        self.obj_attr_name = obj_attr_name if obj_attr_name else name
        self.label = label if label else name
        
    def obj_to_dict(self, obj, data):
        data[self.name] = getattr(obj, self.obj_attr_name)

    def dict_to_obj(self, data, obj):
        if self.name in data:
            setattr(obj, self.obj_attr_name, data[self.name])

    @classmethod
    def type_name(cls):
        return cls.__name__

    @property
    def db_field_name(self):
        return self.name

class CharField(ApiField):
    pass    

class IntegerField(ApiField):
    pass

class TextField(ApiField):
    pass

class DateTimeField(ApiField):
    DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
    def obj_to_dict(self, obj, data):
        val = getattr(obj, self.obj_attr_name)
        # and not isinstance(val, basestring):
        if val != None:
            val = val.strftime(self.DATE_FORMAT)
        data[self.name] = val

    def dict_to_obj(self, data, obj):
        if not self.name in data:
            return
        val = data.get(self.name)
        if val != None and not isinstance(val, datetime):
            val = datetime.strptime(val, self.DATE_FORMAT)
        setattr(obj, self.obj_attr_name, val)


class SimpleForeignKeyField(ApiField):
    def __init__(self, name, label=None, obj_attr_name=None):
        self.name = name + '_id'
        self.obj_attr_name = obj_attr_name if obj_attr_name else self.name
        self.label = label if label else name
