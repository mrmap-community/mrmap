from dataclasses import dataclass
from requests import Request


@dataclass(frozen=True)
class OGCRequestContext:
    service: str
    version: str
    operation: str
    method: str

    @classmethod
    def from_request(cls, request: Request):
        if request.method == "GET":
            params = request.params
            return cls(
                service=params.get("SERVICE", "").lower(),
                version=params.get("VERSION", ""),
                operation=params.get("REQUEST", ""),
                method="GET"
            )

        if request.method == "POST":
            xml = load_xmlobject_from_string(request.data, XmlObject)
            return cls(
                service=xml.service_type.lower(),
                version=xml.version,
                operation=xml.operation,
                method="POST"
            )
