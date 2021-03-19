from django.views.generic.base import ContextMixin
from django.utils.translation import gettext as _
from django_bootstrap_swt.components import Badge
from django_bootstrap_swt.enums import BadgeColorEnum


class OrganizationBasedTemplateRoleDetailContextMixin(ContextMixin):
    object = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab_nav = [{'url': self.object.get_absolute_url,
                    'title': _('Details')},
                   {'url': self.object.get_members_view_uri,
                    'title': _('Members ').__str__() + Badge(content=str(self.object.user_set.count()),
                                                             color=BadgeColorEnum.SECONDARY)},
                   ]
        context.update({"object": self.object,
                        'actions': self.object.get_actions(),
                        'tab_nav': tab_nav,
                        })
        return context
