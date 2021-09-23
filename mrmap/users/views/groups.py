from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views.generic.base import ContextMixin
from django_filters.views import FilterView
from extras.enums.bootstrap import BadgeColorEnum
from extras.views import (SecuredCreateView, SecuredDeleteView, SecuredDependingListMixin,
                          SecuredDetailView, SecuredListMixin, SecuredUpdateView)
from MrMap.icons import IconEnum, get_icon
from MrMap.messages import PUBLISH_REQUEST_ACCEPTED, PUBLISH_REQUEST_DENIED
from MrMap.views import CustomSingleTableMixin

from users.forms.groups import OrganizationChangeForm
from users.models.groups import Organization, PublishRequest
from users.tables.groups import OrganizationDetailTable, OrganizationPublishersTable, PublishesRequestTable


class OrganizationDetailContextMixin(ContextMixin):
    object = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab_nav = [{'url': self.object.get_absolute_url,
                    'title': _('Details')},
                   {'url': self.object.publishers_uri,
                    'title': _('Publishers ').__str__() + f'<span class="badge {BadgeColorEnum.SECONDARY.value}">New</span>'},
                   ]
        context.update({"object": self.object,
                        'actions': self.object.get_actions(),
                        'tab_nav': tab_nav,
                        'publisher_requests_count': PublishRequest.objects.filter(organization=self.object).count()})
        return context


class OrganizationCreateView(SecuredCreateView):
    model = Organization


class OrganizationDetailView(OrganizationDetailContextMixin, SecuredDetailView):
    class Meta:
        verbose_name = _('Details')

    model = Organization
    template_name = 'MrMap/detail_views/table_tab.html'
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = OrganizationDetailTable(
            data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


class OrganizationEditView(SecuredUpdateView):
    model = Organization
    form_class = OrganizationChangeForm 


class OrganizationDeleteView(SecuredDeleteView):
    model = Organization
    queryset = Organization.objects.filter(is_auto_generated=False)

    def get_msg_dict(self):
        return {'name': self.get_object().name}


class OrganizationPublishersTableView(SecuredDependingListMixin, OrganizationDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = Organization
    depending_model = Organization
    table_class = OrganizationPublishersTable
    filterset_fields = {'name': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    object = None
    title = get_icon(IconEnum.PUBLISHERS) + _(' Publish for list')

    def get_queryset(self):
        return self.object.publishers.all()

    def get_table_kwargs(self):
        return {'organization': self.object}


@method_decorator(login_required, name='dispatch')
class PublishRequestNewView(SecuredCreateView):
    model = PublishRequest
    fields = ('group', 'organization', 'message')

    def form_valid(self, form):
        group = form.cleaned_data['group']
        organization = form.cleaned_data['organization']
        if group.publish_for_organizations.filter(id=organization.id).exists():
            form.add_error(
                None, _(f'{group} can already publish for Organization.'))
            return self.form_invalid(form)
        else:
            return super().form_valid(form)


class PublishRequestTableView(SecuredListMixin, FilterView):
    model = PublishRequest
    table_class = PublishesRequestTable
    filterset_fields = ['group', 'organization', 'message']

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            # show only requests for groups or organization where the user is member of
            # superuser can see all pending requests
            queryset.filter(Q(group__in=self.request.user.groups.all()) |
                            Q(organization=self.request.user.organization))
        return queryset


class PublishRequestAcceptView(SecuredUpdateView):
    model = PublishRequest
    fields = ('is_accepted', )
    success_message = PUBLISH_REQUEST_ACCEPTED
    title = _('Accept request')

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ValidationError as e:
            messages.error(self.request, e.message)
            response = HttpResponseRedirect(self.get_success_url())
        return response


class PublishRequestRemoveView(SecuredDeleteView):
    model = PublishRequest
    success_message = PUBLISH_REQUEST_DENIED
    title = _('Deny request')
