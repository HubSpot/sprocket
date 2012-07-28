
def magic_enum_meta_cls(typ, *args, **kwargs):
    attrs = {}
    for key, value in args[1].items():
        if isinstance(value, Val):
            attrs[key] = key
        else:
            attrs[key] = value
    return type(typ, args[0], attrs, **kwargs)


class MagicEnum(object):

    def __new__(typ, *args, **kwargs):
        obj = object.__new__(typ, *args, **kwargs)
        obj.values = []
        import pdb; pdb.set_trace()
        for attr_name in dir(obj.__class__):
            val = getattr(obj.__class__, attr_name)
            if isinstance(val, Val):
                setattr(obj, attr_name, attr_name)
                obj.values.append(attr_name)
        return obj

class Val(object):
    pass
