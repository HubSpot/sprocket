

class MagicEnum(object):
    def __new__(typ, *args, **kwargs):
        obj = object.__new__(typ, *args, **kwargs)
        obj.values = []
        for attr_name in dir(obj.__class__):
            val = getattr(obj.__class__, attr_name)
            if isinstance(val, Val):
                setattr(obj, attr_name, attr_name)
                obj.values.append(attr_name)
        return obj

class Val(object):
    pass
