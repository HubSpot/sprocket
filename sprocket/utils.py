
class Val(object):
    pass


def magic_enum_meta_cls(typ, *args, **kwargs):
    attrs = {}
    for key, value in args[1].items():
        if isinstance(value, Val):
            attrs[key] = key
        else:
            attrs[key] = value
    return type(typ, args[0], attrs, **kwargs)


class MagicEnum(object):
    __metaclass__ = magic_enum_meta_cls

