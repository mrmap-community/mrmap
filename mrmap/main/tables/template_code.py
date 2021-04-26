VALUE_ABSOLUTE_LINK = """
<a href="{{value.get_absolute_url}}">{{value}}</a>
"""

RECORD_ABSOLUTE_LINK = """
{% if record.get_absolute_url %}<a href="{{record.get_absolute_url}}">{{record}}</a>{% else %}{{record}}{% endif %}
"""

VALUE_BADGE = """
<span class="badge {{color}}">{{value}}</span>
"""
