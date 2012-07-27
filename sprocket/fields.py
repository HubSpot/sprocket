

class ApiField(object):
    def __init__(self, name, label=None, obj_attr_name=None):
        self.name = name
        self.obj_attr_name = obj_attr_name if obj_attr_name else name
        self.label = label if label else name
        
    def obj_to_dict(self, obj, data):
        data[self.name] = getattr(obj, self.obj_attr_name)

    def dict_to_obj(self, data, obj):
        if self.name in data:
            setattr(obj, self.obj_attr_name, data[self.name])

        
