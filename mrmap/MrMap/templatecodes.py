PROGRESS_BAR = """
<div class="progress">
  <div class="progress-bar{% if striped %} progress-bar-striped{% endif %}{% if animated %} progress-bar-animated{% endif %} {{color}}" role="progressbar" aria-valuenow="{{value}}" aria-valuemin="0" aria-valuemax="{{total}}" style="width: {{value}}%">{{value}}%</div>
</div>
"""
TOOLTIP = """
<span class="d-inline-block" tabindex="0" data-toggle="tooltip" title="{{tooltip}}">{{content}}</span>
"""
