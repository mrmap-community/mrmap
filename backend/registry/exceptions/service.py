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
