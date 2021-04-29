VALUE_ABSOLUTE_LINK = """
<a href="{{value.get_absolute_url}}">{{value}}</a>
"""

VALUE_ABSOLUTE_LINK_LIST = """
{% for val in value %}
<a href="{{val.get_absolute_url}}">{{val}}</a>,
{% endfor %}
"""

RECORD_ABSOLUTE_LINK = """
{% if record.get_absolute_url %}<a href="{{record.get_absolute_url}}">{{record}}</a>{% else %}{{record}}{% endif %}
"""


VALUE_BADGE = """
<span class="badge {% if color %}{{color}}{% else %}badge-info{% endif %}">{{value}}</span>
"""

VALUE_BADGE_LIST = """
{% for val in value %}
<span class="badge {% if color %}{{color}}{% else %}badge-info{% endif %}">{{val}}</span>
{% endfor %}
"""