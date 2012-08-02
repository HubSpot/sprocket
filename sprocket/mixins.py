




class BaseMixin(object):
    def __init__(self, api_resource):
        self.api = api_resource
        self.event_handler_by_event_name = self._construct_events_dict()
        
    def _construct_events_dict(self):
        handlers_by_name = {}
        for attr_name in dir(self):
            if attr_name.startswith('on_'):
                event_name = attr_name[3:]
                handlers_by_name[event_name] = getattr(self, attr_name)
        return handlers_by_name

    def get_handler_for_event(self, event_name):
        return self.event_handler_by_event_name.get(event_name, None)

    def get_endpoints(self):
        return []
