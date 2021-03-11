from breadcrumb.breadcrumb import BreadCrumbBuilder


def breadcrumb_renderer(request):
    return {'BREADCRUMB_CONFIG': BreadCrumbBuilder(path=request.path).breadcrumb}
