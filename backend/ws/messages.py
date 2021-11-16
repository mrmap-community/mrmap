from django.utils import timezone
from django.template import Context, Template

from MrMap.templatecodes import TOAST


class Toast:
    """
    helper class to setup the response for a Toast notification
    """
    rendered = None

    def __init__(self, title: str, body: str):
        self.title = title
        self.body = body
        self.timestamp = timezone.now()
        self.template_code = TOAST

    def __str__(self):
        if not self.rendered:
            self.render()
        return self.rendered

    def render(self):
        context = Context()
        context.update(self.__dict__)
        self.rendered = Template(template_string=self.template_code).render(context=context)

    def get_response(self):
        return {'toast': self.__str__()}
