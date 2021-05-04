PROGRESS_BAR = """
<div class="progress">
  <div class="progress-bar{% if striped %} progress-bar-striped{% endif %}{% if animated %} progress-bar-animated{% endif %} {{color}}" role="progressbar" aria-valuenow="{{value}}" aria-valuemin="0" aria-valuemax="{{total}}" style="width: {{value}}%">{{value}}%</div>
</div>
"""
TOOLTIP = """
<span class="d-inline-block" tabindex="0" data-toggle="tooltip" title="{{tooltip}}">{{content}}</span>
"""
TOAST = """
<div class="toast" data-autohide="false">
    <div class="toast-header">
        <svg class=" rounded mr-2" width="20" height="20" xmlns="http://www.w3.org/2000/svg"
            preserveAspectRatio="xMidYMid slice" focusable="false" role="img">
            <rect fill="#007aff" width="100%" height="100%" /></svg>
        <strong class="mr-auto">{{title}}</strong>
        <small class="ml-1 text-muted">{{ timestamp|date:"r" }}</small>
        <button type="button" class="ml-2 mb-1 close" data-dismiss="toast" aria-label="Close">
            <span aria-hidden="true">&times;</span>
        </button>
    </div>
    <div class="toast-body">
        {{body}}
    </div>
</div>
"""
