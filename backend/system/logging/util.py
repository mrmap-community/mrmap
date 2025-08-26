import re
from typing import Any, Dict


def parse_rfc5424_message(msg: str) -> Dict[str, Any]:
    """
    Zerlegt eine durch RFC5424Formatter erzeugte Logzeile zurück in ihre Einzelteile.
    Gibt Dict mit header-Feldern, structured_data und message zurück.
    """
    result: Dict[str, Any] = {}

    # Regex grob: "1 TIMESTAMP HOST APP PROCID - [SD...] MESSAGE"
    # Structured Data kann mehrfach vorkommen → separate Extraktion
    header_re = re.compile(
        r'^1\s+'
        r'(?P<timestamp>\S+)\s+'
        r'(?P<host>\S+)\s+'
        r'(?P<app>\S+)\s+'
        r'(?P<procid>\S+)\s+'
        r'(?P<msgid>-)\s+'
        r'(?P<rest>.*)$'
    )

    m = header_re.match(msg)
    if not m:
        raise ValueError("Nachricht entspricht nicht RFC5424-Format")

    result["version"] = "1"
    result["timestamp"] = m.group("timestamp")
    result["host"] = m.group("host")
    result["app"] = m.group("app")
    result["procid"] = m.group("procid")
    result["msgid"] = m.group("msgid")

    rest = m.group("rest")

    # Structured Data: Sequenz von [..]
    sd_re = re.compile(r'(\[.*?\])')
    sd_parts = sd_re.findall(rest)

    structured_data = {}
    for sd in sd_parts:
        # Beispiel: [metaSDID@split related_id="..." part="1" total="3"]
        inside = sd[1:-1].strip()
        tokens = inside.split()
        sdid = tokens[0]
        kv = {}
        for token in tokens[1:]:
            if "=" not in token:
                continue
            key, val = token.split("=", 1)
            if val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            # Unescape nach RFC5424
            val = val.replace("\\\"", "\"").replace(
                "\\\\", "\\").replace("\\]", "]")
            kv[key] = val
        structured_data[sdid] = kv

    result["structured_data"] = structured_data

    # Nachricht ist nach dem letzten SD-Block
    if sd_parts:
        last_sd = sd_parts[-1]
        msg_index = rest.rfind(last_sd) + len(last_sd)
        free_message = rest[msg_index:].lstrip()
    else:
        free_message = rest.strip()

    result["message"] = free_message
    return result


def format_structured_data(structured_data: Dict):
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


def unescape_sd_value(value: str) -> str:
    """
    Entschärft einen SD-PARAM-Wert nach RFC5424.
    """
    if not isinstance(value, str):
        value = str(value)

    # Reihenfolge wichtig: erst \\ ersetzen, dann die anderen Escapes
    return (
        value.replace("\\n", "\n")
             .replace("\\r", "\r")
             .replace("\\]", "]")
             .replace("\\\"", "\"")
             .replace("\\\\", "\\")
    )


def get_string_length(value):
    return len(value.encode("utf-8"))
