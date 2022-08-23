def remove_from_list_by_name(list, name):
    obj_to_be_remove = next((obj for obj in list if obj == name), None)
    if obj_to_be_remove:
        list.remove(list.index(obj_to_be_remove))
