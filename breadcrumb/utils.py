from django.urls import resolve, Resolver404


def check_path_exists(path):
    try:
        match = resolve(path=path)
        return match
    except Resolver404:
        return None
