def remove_from_list_by_name(list, name):
    obj_to_be_remove = next((obj for obj in list if obj == name), None)
    if obj_to_be_remove:
        list.remove(list.index(obj_to_be_remove))


def get_xml_mapper(capabilities_xml):
    # TODO: get the corret xml mapper based on the information found inside the given capabilities xml
    pass
