from collections import OrderedDict
from breadcrumb.utils import check_path_exists


class BreadCrumbItem:
    def __init__(self, path: str,
                 is_representative: bool = True,
                 is_specific: bool = False,
                 is_active_path: bool = False):
        self.path = path
        self.is_representative = is_representative
        self.is_specific = is_specific
        self.is_active_path = is_active_path


class BreadCrumbBuilder:
    breadcrumb = None

    def __init__(self, path: str):
        self.path = path
        self.build_breadcrumb()

    def build_breadcrumb(self):
        path_items = self.path.split("/")
        path_items.pop(0)
        path_tmp = ""

        self.breadcrumb = OrderedDict()
        for path_item in path_items:
            path_tmp += "/" + path_item
            match = check_path_exists(path_tmp)
            if match:
                is_specific = True if 'pk' in match.kwargs and 'pk' in match.route.split("/")[-1] else False
                is_active_path = True if self.path == path_tmp else False
                breadcrumb_item = BreadCrumbItem(is_representative=True,
                                                 path=path_tmp,
                                                 is_specific=is_specific,
                                                 is_active_path=is_active_path)
                self.breadcrumb[path_item] = breadcrumb_item
            else:
                self.breadcrumb[path_item] = BreadCrumbItem(is_representative=False,
                                                            path=path_tmp)
        return self.breadcrumb
