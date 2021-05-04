from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist


def default_task_handler(**kwargs):
    if 'created_by_user_pk' in kwargs:
        try:
            user = get_user_model().objects.get(id=kwargs['created_by_user_pk'])
            set_current_user(user)
        except ObjectDoesNotExist:
            return
