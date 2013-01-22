

class Authentication(object):
    def authenticate(self, request, endpoint):
        raise NotImplementedError("Need to implement in a base class")

class DefaultAuthentication(Authentication):
    def authenticate(self, request, endpoint):
        return request.user.is_authenticated()

class NoAuthentication(Authentication):
    def authenticate(self, request, endpoint):
        return True
