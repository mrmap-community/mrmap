def split(context, value, token):
    values = []
    if isinstance(value, list):
        for v in value:
            values.extend(v.split(token))
    else:
        values = value.split(token)
    return values
