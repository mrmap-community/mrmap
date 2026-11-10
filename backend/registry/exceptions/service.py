class LayerNotQueryable(Exception):
    """Raised when the layer is not queryable"""
    pass


class OperationNotSupported(Exception):
    """Raised when the service does not support the operation"""
    pass


class NoContent(Exception):
    """Raised when remote metadata is empty"""
    pass


class CapabilitiesBackupMissing(Exception):
    """A service row names a capabilities backup the storage does not hold.

    The database names an ``xml_backup_file`` which the media storage does
    not have - the "corrupted service" of the removed url fallback. This is
    an integrity error of the deployment, not a remote condition, and a
    read of the service does not work around it (#1044): the document comes
    back through verified storage restoration or through the service's
    update workflow, which fetches ``remote_capabilities`` explicitly and
    stages the answer as a candidate. Nothing on that recovery path happens
    implicitly while a service is being read.
    """

    def __init__(self, service, missing_path: str):
        self.service_type = service.service_type
        self.service_pk = str(service.pk)
        self.missing_path = missing_path
        super().__init__(
            f"{service} has no capabilities file stored at "
            f"'{missing_path}'. Reads never fall back to the remote service: "
            f"restore the document on the storage or run a "
            f"{self.service_type} update job for {self.service_pk}.")


class DuplicateLayerIdentifiers(Exception):
    """A capabilities document which lists one layer name more than once.

    ``registry.models.Layer`` keeps one row per ``(service, identifier)``
    while a document may re-list the same ``<Name>`` under several parents -
    swisstopo BGDI 169, IGN geopf 35, 41 further services in one demo run
    (#1200). Persisting such a document died with a raw psycopg
    ``UniqueViolation`` on ``unique_identifer_per_wms``: the whole
    registration disappeared and the activity popover showed the constraint
    dump. The decision on #1200 keeps the unique constraint - services with
    duplicated layers are not allowed - so this error refuses the document
    with the duplicated identifiers named, while the worker is still
    processing the document instead of the database refusing rows.
    """

    # The message travels into the ``phase`` of the background process, a
    # 512 char column composed with "An error occurred: " on failure; a
    # document with hundreds of duplicates may not overflow it.
    MAX_NAMED_IDENTIFIERS = 5
    MAX_IDENTIFIER_LENGTH = 60

    def __init__(self, duplicated):
        self.duplicated = sorted(duplicated)
        named = [
            name if len(name) <= self.MAX_IDENTIFIER_LENGTH
            else name[:self.MAX_IDENTIFIER_LENGTH - 1] + "…"
            for name in self.duplicated[:self.MAX_NAMED_IDENTIFIERS]]
        message = (
            "The capabilities document contains duplicate layer names: "
            + ", ".join(f"'{name}'" for name in named))
        remaining = len(self.duplicated) - len(named)
        if remaining > 0:
            message += f" and {remaining} more"
        message += (". Mr. Map does not build services whose capabilities "
                    "list a layer name more than once.")
        super().__init__(message)


class CapabilitiesPersistenceError(Exception):
    """A capabilities document whose rows the database refused to store.

    The document parsed and the build reached persistence, but the schema
    rejected a row the document describes. #1201 lost a WMS over a
    ``LegendURL`` without the optional ``width``/``height`` attributes while
    ``registry.models.LegendUrl`` required them; the raw psycopg
    ``IntegrityError`` - constraint name, ``DETAIL: Failing row contains
    (...)`` and all - was the only thing the activity popover and the
    ``TaskResult`` showed. This class names the refusal as a defined failure
    of the build, keeping the driver's full dump in the cause it is raised
    from, which the worker log still carries.
    """

    def __init__(self, integrity_error: Exception):
        self.integrity_error = integrity_error
        # Django wraps the driver error and keeps it as the cause; the
        # psycopg diagnostic names the refused row precisely, without the
        # DETAIL blob which the stringified IntegrityError appends
        diagnostic = getattr(
            getattr(integrity_error, "__cause__", None), "diag", None)
        detail = (getattr(diagnostic, "message_primary", None)
                  or str(integrity_error).splitlines()[0])
        super().__init__(
            f"The capabilities document could not be persisted: {detail}")
