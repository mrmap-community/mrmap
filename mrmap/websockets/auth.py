from channels.auth import AuthMiddleware
from channels.exceptions import DenyConnection
from channels.sessions import CookieMiddleware, SessionMiddleware


class OnlyAuthUserMiddleware(AuthMiddleware):
    def __call__(self, scope, receive, send):
        ret = super().__call__(scope, receive, send)
        print(scope)
        if scope['user'].is_anonymous:
            raise DenyConnection
        return ret


# Handy shortcut for applying all three layers at once
def OnlyAuthMiddlewareStack(inner):
    return CookieMiddleware(SessionMiddleware(OnlyAuthUserMiddleware(inner)))
