import sqlparse


def interpolate_sql(sql, params):
    try:
        if params is None:
            return sql
        if isinstance(params, (list, tuple)):
            interpolated = sql % tuple(repr(p) for p in params)
        elif isinstance(params, dict):
            interpolated = sql % {k: repr(v) for k, v in params.items()}
        else:
            interpolated = sql
        # Format SQL for readability
        return sqlparse.format(interpolated, reindent=True, keyword_case='upper')
    except Exception as e:
        return f"{sql} -- [Interpolation failed: {e}]"


def format_structured_data(structured_data: dict):
    extra_sd_elements = []
    for sdid, key_value_pairs in structured_data.items():
        sd = f"[{sdid}"
        for key, value in key_value_pairs.items():
            sd += f' {key}="{escape_sd_value(value)}"'
        sd += "]"
        extra_sd_elements.append(sd)

    return f"{''.join(extra_sd_elements)}"


def escape_sd_value(value: str) -> str:
    """
    Escaped einen SD-PARAM-Wert nach RFC5424.
    """
    if not isinstance(value, str):
        value = str(value)

    return (
        value.replace("\\", "\\\\")
             .replace("\"", "\\\"")
             .replace("]", "\\]")
             .replace("\n", "\\n")
             .replace("\r", "\\r")
    )
