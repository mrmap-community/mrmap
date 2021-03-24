from main.tables.columns import GenericButtonsColumn
from structure.models import PublishRequest, Organization


class PublishesRequestButtonsColumn(GenericButtonsColumn):
    """
    Render accept and deny buttons for PublishRequest.
    """
    model = PublishRequest
    # Note that braces are escaped to allow for string formatting prior to template rendering
    template_code = """
    {{% load static i18n %}}
    {{% load guardian_tags %}}
    {{% get_obj_perms request.user for record as "obj_perms" %}}

    {{% if "change_pendingrequest" in perms %}}
    <div class="d-inline-flex">
        <form class="mr-1" action="{{% url '{app_label}:{model_name}_change' {pk_field}=record.{pk_field} %}}" method="post">
          {{% csrf_token %}}
          <input type="hidden"  name="is_accepted" value="on">
          <button type="submit" class="btn btn-sm btn-success" data-toggle="tooltip" data-placement="top" title="{{% trans 'Accept request' %}}">{{{{ ICONS.OK|safe }}}}</button>
        </form>
        <form action="{{% url '{app_label}:{model_name}_change' {pk_field}=record.{pk_field} %}}" method="post">
          {{% csrf_token %}}
          <input type="hidden"  name="is_accepted" value="off">
          <button type="submit" class="btn btn-sm btn-danger" data-toggle="tooltip" data-placement="top" title="{{% trans 'Deny request' %}}">{{{{ ICONS.NOK|safe }}}}</button>
        </form>
    </div>
    {{% endif %}}
    """


class RemovePublisherButtonColumn(GenericButtonsColumn):
    """
    Render remove link button for publisher.
    """
    model = Organization
    # Note that braces are escaped to allow for string formatting prior to template rendering
    template_code = """
    {{% load static i18n %}}
    {{% load guardian_tags %}}
    {{% get_obj_perms request.user for record as "obj_perms" %}}

    {{% if "change_organization" in perms %}}
    <a class="btn btn-sm btn-danger" href="{{% url '{app_label}:{model_name}_change' {pk_field}=record.{pk_field} %}}" data-toggle="tooltip" data-placement="top" title="{{% trans 'remove publisher' %}}">{{{{ ICONS.REMOVE|safe }}}}</a>
    {{% endif %}}
    """


class EditRoleButtonColumn(GenericButtonsColumn):
    """
    Render remove link button for publisher.
    """
    model = Organization
    # Note that braces are escaped to allow for string formatting prior to template rendering
    template_code = """
    {{% load static i18n %}}
    {{% load guardian_tags %}}
    {{% get_obj_perms request.user for record as "obj_perms" %}}

    {{% if "change_ownerbasedtemplaterole" in perms %}}
    <a class="btn btn-sm btn-warning" href="{{% url '{app_label}:ownerbasedtemplaterole_change' {pk_field}=record.{pk_field} %}}" data-toggle="tooltip" data-placement="top" title="{{% trans 'edit members' %}}">{{{{ ICONS.EDIT|safe }}}}</a>
    {{% endif %}}
    """