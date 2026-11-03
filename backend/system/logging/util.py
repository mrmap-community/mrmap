"""The sql of a slow request, with the parameters it was asked with.

The dumps of the slow request logging are the artifact an analyzer greps when a
request was slow, which makes the statement they carry worth as much as the
statement itself: it has to run. Interpolated with the ``repr`` of a value it does
not - ``datetime.timedelta(0)`` and ``UUID('beeacc4e-…')`` are no sql, the first of
them answers ``ERROR: schema "datetime" does not exist`` when it is pasted into psql,
and while the analyzer is chasing that schema the statement hides which of its
aggregations were parameterized at all (#887).
"""

from django.db import connection
from psycopg import sql as psycopg_sql


def quote_parameter(param):
    """One parameter as the sql literal which its type answers for.

    Asked of the driver rather than answered by Python: ``psycopg.sql.Literal`` hands
    the value to the adapter which the connection answers for its type, so the result
    is a literal Postgres reads - ``'0:00:00'::interval`` where ``repr`` answered
    ``datetime.timedelta(0)``, and ``'beeacc4e…'::uuid`` where it answered
    ``UUID('beeacc4e-…')``.

    A statement is interpolated for the dump, never executed here, so two cases have
    to be survived: a type the driver has no adapter for, and a database whose
    quoting the adapters of an open connection know better than the global ones.
    Both fall back on ``repr``, which is what the dump carried before and what a
    reader can still read.
    """
    try:
        # the raw connection of django, which is the psycopg connection when one is
        # open and None otherwise; None leaves psycopg the global adapters
        return psycopg_sql.Literal(param).as_string(connection.connection)
    except Exception:
        return repr(param)


def interpolate_sql(sql, params):
    try:
        if params is None:
            return sql
        if isinstance(params, (list, tuple)):
            interpolated = sql % tuple(quote_parameter(p) for p in params)
        elif isinstance(params, dict):
            interpolated = sql % {k: quote_parameter(v) for k, v in params.items()}
        else:
            interpolated = sql
        return interpolated
    except (TypeError, ValueError, KeyError) as e:
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
