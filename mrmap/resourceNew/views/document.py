from main.views import SecuredDetailView
from resourceNew.models.document import Document
from django.http import HttpResponse


class DocumentDetailView(SecuredDetailView):
    model = Document
    content_type = "application/xml"
    slug_field = "uuid"
    slug_url_kwarg = "uuid"
    # to avoid multiple objects error; we show always the custom document
    queryset = Document.objects.filter(is_original=False)

    def render_to_response(self, context, **response_kwargs):
        return HttpResponse(content=self.object.content,
                            content_type=self.content_type)
