"""Idempotent persistence of selected monitoring probe preview candidates.

The apply action of the monitoring epic consumes the candidates of the preview
endpoint of #742. This module is the server side of that hand-off:

* **Revalidation against the CURRENT capabilities.** Every submitted candidate
  is re-identified against ``current_candidate_map`` of
  ``registry.helper.monitoring_generation``; a candidate an outdated preview
  proposed for capabilities which changed since (the element is gone,
  deactivated, no longer requestable...) is refused with ``stalePreview`` and
  the client is asked for a fresh preview. The submitted parameters are
  validated against the CURRENT proposal — the preview passthrough is never
  trusted: CRS and formats must be advertised for the element, dimensions,
  counts and timeouts must stay inside the generator bounds, and the target of
  a candidate can not be swapped for another one.
* **Idempotence.** Each persisted generated probe carries
  ``generator_identity`` (see ``generated_identity``: service + probe type +
  element identifiers, never display names) and the probe models pin it with
  a partial unique constraint among the generated probes. Repeated, retried
  and concurrent applies race into that constraint; the losing apply
  recognizes the row the winner wrote and updates or preserves it instead of
  duplicating it.
* **Customization rule.** The stored parameters of a generated probe are
  compared against the regeneration's CURRENT parameters — the proposal
  ``current_candidate_map`` answers for the same identity with the
  generator's default request parameters. A generated probe whose stored
  parameters differ from that regeneration is considered user-customized and
  its stored parameters are PRESERVED unless the request explicitly carries
  ``confirmReplace``. (Capabilities which changed in a way that keeps the
  candidate identity — e.g. an updated element extent — are indistinguishable
  from a user edit; treating them as a customization is the conservative
  reading of the epic: never overwrite without confirmation.) A probe which
  is not customized receives the submitted (possibly edited) parameters.
* **Manual probes are never touched.** They carry no generator identity, can
  not match a candidate and are not read by the apply beyond the count of
  generated probes of the service.
* **No schedule activation.** The apply writes probes onto an existing,
  explicitly selected monitoring setting. It never creates a setting, never
  changes its ``enabled`` state and never touches its schedule — activating
  the periodic execution stays the explicit action it is.
* **Bounds.** At most ``MAX_PROBES`` candidates per apply, and a service holds
  at most ``MAX_PROBES`` generated probes in total; the execution side of the
  bound is the chunked dispatch of ``registry.tasks.monitoring``.

Which probe type means which model, parameters and comparisons is described by
the :class:`ProbeSpec` of its ``(service type, probe type)`` pair, so a web
feature service candidate is validated and stored by the rules of its own
operation instead of a branch of the WMS code.
"""
from django.contrib.gis.gdal import GDALException
from django.contrib.gis.geos import Polygon
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from registry.enums.monitoring import ProbeOriginEnum
from registry.helper.monitoring_generation import (
    GENERATOR_VERSION, IMPLEMENTED_PRESETS, MAX_FEATURE_COUNT,
    MAX_IMAGE_DIMENSION, MAX_PROBES, MAX_TIMEOUT, PRESET_STANDARD,
    current_candidate_map, generated_identity)
from registry.helper.monitoring_generation_wfs import MAX_FEATURES
from registry.models.metadata import MimeType, ReferenceSystem
from registry.models.monitoring import (
    GetCapabilitiesProbe, GetFeatureInfoProbe, GetMapProbe,
    WebFeatureServiceDescribeFeatureTypeProbe,
    WebFeatureServiceGetCapabilitiesProbe, WebFeatureServiceGetFeatureProbe,
    WebFeatureServiceMonitoringSetting, WebMapServiceMonitoringSetting)

WORLD_EXTENT = (-180.0, -90.0, 180.0, 90.0)

#: the monitoring setting model whose probes an apply may write, per service
#: type. The apply needs change on the setting of the service it runs on —
#: never on a setting of another service type.
SETTING_MODEL = {
    "WMS": WebMapServiceMonitoringSetting,
    "WFS": WebFeatureServiceMonitoringSetting,
}


class ApplyError(Exception):
    """A refusal of the apply action, answered as ``{"error": code, ...}``."""

    def __init__(self, code, status=400, detail=None):
        self.code = code
        self.status = status
        self.detail = detail or {}


def _bbox(value):
    """The validated geographic extent of a bounding box [w, s, e, n]."""
    try:
        values = tuple(float(part) for part in value)
    except (TypeError, ValueError):
        raise ApplyError("parameters", 400, {"field": "bbox"})
    if len(values) != 4:
        raise ApplyError("parameters", 400, {"field": "bbox"})
    west, south, east, north = values
    min_west, min_south, max_east, max_north = WORLD_EXTENT
    if not (min_west <= west <= east <= max_east
            and min_south <= south <= north <= max_north):
        raise ApplyError("parameters", 400, {"field": "bbox"})
    return (west, south, east, north)


def _bounded_int(value, field, maximum, minimum=1):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ApplyError("parameters", 400, {"field": field})
    if not minimum <= number <= maximum:
        raise ApplyError("parameters", 400, {"field": field})
    return number


def _boolean(value, field):
    if not isinstance(value, bool):
        raise ApplyError("parameters", 400, {"field": field})
    return value


def _reference_system(crs: str) -> ReferenceSystem:
    """The lookup row of a CRS, created when the registry does not know it.

    Reference systems are lookup rows which imports create with
    ``get_or_create``; a generated probe must be able to express the CRS it
    proposes even when no document carried this one before.
    """
    prefix, _, code = crs.partition(":")
    try:
        with transaction.atomic():
            return ReferenceSystem.objects.get_or_create(
                prefix=prefix, code=code)[0]
    except IntegrityError:
        # a concurrent apply created the lookup row in the meantime
        return ReferenceSystem.objects.get(prefix=prefix, code=code)


def _mime_type(mime_type: str) -> MimeType:
    try:
        with transaction.atomic():
            return MimeType.objects.get_or_create(
                mime_type=mime_type)[0]
    except IntegrityError:
        return MimeType.objects.get(mime_type=mime_type)


class ProbeSpec:
    """What one probe type of one service type needs to be applied.

    A spec knows the concrete model of its probe type, the preview parameters
    it accepts, the target key of its candidate and how to compare the stored
    parameters of a probe with the regeneration of the same candidate.
    """

    #: the concrete probe model this spec writes
    model = None
    #: the candidate key naming the element the probe targets, None for a
    #: probe which targets the service itself
    target_key = None
    #: the preview parameter names one candidate of this type may carry; a name
    #: outside the whitelist is refused instead of being ignored silently
    parameters = frozenset({"timeout", "maxResponseBytes"})

    def __init__(self, model=None):
        # the same spec class serves both service types, whose GetCapabilities
        # probes are different models
        if model is not None:
            self.model = model

    def target(self, candidate):
        """The element a candidate targets, None for a service wide probe."""
        return candidate.get(self.target_key) if self.target_key else None

    def identities(self, candidate):
        """The element identifiers the stable identity of a candidate keys on."""
        target = self.target(candidate)
        return [target["identifier"]] if target else []

    def _reject_unknown(self, probe_type, parameters):
        if not isinstance(parameters, dict):
            raise ApplyError("parameters", 400, {"field": "parameters"})
        unknown = set(parameters) - self.parameters
        if unknown:
            raise ApplyError("parameters", 400, {
                "field": "parameters", "unknown": sorted(unknown)})

    def _timeout(self, parameters, proposed):
        return _bounded_int(
            parameters.get("timeout", proposed.get("timeout")),
            "timeout", MAX_TIMEOUT)

    def _element(self, parameters, candidate, names):
        """The target of the candidate, which a submission can never re-point."""
        target = self.target(candidate)
        for name in names:
            if name in parameters:
                expected = ([target["identifier"]] if name == names[0]
                            else [str(target["id"])])
                if list(parameters.get(name) or []) != expected:
                    # the stable identity binds the candidate to its element; a
                    # submitted edit can never silently re-point the probe
                    raise ApplyError("parameters", 400, {
                        "field": name, "expected": expected})
        return target

    def _one_of(self, value, field, advertised):
        """A submitted format or CRS which must be one the service advertises."""
        if advertised and value not in advertised:
            raise ApplyError("parameters", 400, {
                "field": field, "expected": sorted(advertised)})
        return value

    def validate(self, probe_type, parameters, candidate):
        """The validated, persistable subset of one submitted candidate.

        The whitelist of the probe type is the gate in front of the concrete
        validation: a parameter name the generator never proposes is refused
        instead of being silently ignored.
        """
        self._reject_unknown(probe_type, parameters)
        return self.desired(probe_type, parameters, candidate)

    def desired(self, probe_type, parameters, candidate):
        """The persistable subset, validated against the current candidate."""
        proposed = candidate["parameters"]
        return {"timeout": self._timeout(parameters, proposed)}

    def stored(self, probe):
        """The stored parameters of a probe, in the shape of ``validate``."""
        return {"timeout": probe.timeout}

    def regenerated(self, probe_type, parameters):
        """The regeneration of a candidate, in the shape of ``stored``."""
        return {"timeout": parameters.get("timeout")}

    def values(self, desired):
        """The model values beyond the common provenance and timeout."""
        return {}

    def relations(self, desired):
        """The many to many relations of a newly created probe."""
        return {}

    def write(self, probe, desired):
        """Write validated parameters onto a probe row (never its setting)."""
        probe.timeout = desired["timeout"]
        probe.save()


class CapabilitiesProbeSpec(ProbeSpec):
    """The GetCapabilities probe of a service, proposed without any target."""


class GetMapProbeSpec(ProbeSpec):
    """The GetMap probe of a named layer of a WMS."""

    model = GetMapProbe
    target_key = "targetLayer"
    parameters = frozenset({
        "layers", "layerIds", "styles", "crs", "crsId", "format", "formatId",
        "bbox", "requestBbox", "axisOrder", "width", "height", "timeout",
        "maxResponseBytes", "exceptions", "dimensionDefaults", "time",
        "elevation"})

    def desired(self, probe_type, parameters, candidate):
        desired = {"timeout": self._timeout(parameters, candidate["parameters"])}
        target = self._element(
            parameters, candidate, ("layers", "layerIds"))

        proposed = candidate["parameters"]
        crs = (parameters.get("crs") or proposed["crs"]).upper()
        self._one_of(crs, "crs", {
            value.upper() for value in candidate["supported"]["crs"]})
        image_format = parameters.get("format") or proposed["format"]
        self._one_of(image_format, "format", candidate["supported"]["formats"])

        desired.update({
            "crs": crs,
            "format": image_format,
            "layer_id": target["id"],
            "width": _bounded_int(
                parameters.get("width", proposed["width"]), "width",
                MAX_IMAGE_DIMENSION),
            "height": _bounded_int(
                parameters.get("height", proposed["height"]), "height",
                MAX_IMAGE_DIMENSION),
            "bbox": _bbox(parameters.get("bbox", proposed["bbox"])),
        })
        return desired

    def stored(self, probe):
        layers = list(probe.layers.values_list("identifier", "pk"))
        polygon = probe.bbox_lat_lon
        return {
            "timeout": probe.timeout,
            "crs": (str(probe.reference_system).upper()
                    if probe.reference_system_id else None),
            "format": str(probe.format) if probe.format_id else None,
            "layer_id": str(layers[0][1]) if layers else None,
            "width": probe.width,
            "height": probe.height,
            "bbox": _bbox(polygon.extent) if polygon is not None else None,
        }

    def regenerated(self, probe_type, parameters):
        return {
            "timeout": parameters.get("timeout"),
            "crs": str(parameters.get("crs")).upper(),
            "format": parameters.get("format"),
            "layer_id": str(parameters["layerIds"][0]),
            "width": parameters.get("width"),
            "height": parameters.get("height"),
            "bbox": _bbox(parameters["bbox"]),
        }

    def values(self, desired):
        return {
            "width": desired["width"],
            "height": desired["height"],
            "reference_system": _reference_system(desired["crs"]),
            "format": _mime_type(desired["format"]),
            "bbox_lat_lon": _polygon(desired["bbox"]),
        }

    def relations(self, desired):
        return {"layers": [desired["layer_id"]]}

    def write(self, probe, desired):
        for name, value in self.values(desired).items():
            setattr(probe, name, value)
        probe.timeout = desired["timeout"]
        probe.save()
        for relation, ids in self.relations(desired).items():
            getattr(probe, relation).set(ids)


class GetFeatureInfoProbeSpec(ProbeSpec):
    """The comprehensive GetFeatureInfo probe of a layer of a WMS.

    Only the parameters the model stores are compared; the extent of the
    request comes from the GetMap probe of the same setting, so a candidate
    without that probe is never proposed by the generator in the first place.
    """

    model = GetFeatureInfoProbe
    target_key = "targetLayer"
    parameters = frozenset({
        "layers", "layerIds", "infoFormat", "infoFormatId", "i", "j",
        "featureCount", "timeout", "maxResponseBytes",
        "checkResponseFormat"})

    def desired(self, probe_type, parameters, candidate):
        desired = {"timeout": self._timeout(parameters, candidate["parameters"])}
        target = self._element(
            parameters, candidate, ("layers", "layerIds"))
        proposed = candidate["parameters"]

        info_format = parameters.get("infoFormat") or proposed["infoFormat"]
        self._one_of(info_format, "infoFormat",
                     candidate["supported"]["infoFormats"])

        desired.update({
            "layer_id": target["id"],
            "info_format": info_format,
            "i": _bounded_int(
                parameters.get("i", proposed["i"]), "i",
                MAX_IMAGE_DIMENSION),
            "j": _bounded_int(
                parameters.get("j", proposed["j"]), "j",
                MAX_IMAGE_DIMENSION),
            "feature_count": _bounded_int(
                parameters.get("featureCount", proposed["featureCount"]),
                "featureCount", MAX_FEATURE_COUNT),
            "check_response_format": _boolean(
                parameters.get("checkResponseFormat",
                               proposed["checkResponseFormat"]),
                "checkResponseFormat"),
        })
        return desired

    def stored(self, probe):
        return {
            "timeout": probe.timeout,
            "layer_id": str(probe.layer_id) if probe.layer_id else None,
            "info_format": str(probe.info_format) if probe.info_format_id else None,
            "i": probe.i,
            "j": probe.j,
            "feature_count": probe.feature_count,
            "check_response_format": probe.check_response_format,
        }

    def regenerated(self, probe_type, parameters):
        return {
            "timeout": parameters.get("timeout"),
            "layer_id": str(parameters["layerIds"][0]),
            "info_format": parameters["infoFormat"],
            "i": parameters["i"],
            "j": parameters["j"],
            "feature_count": parameters["featureCount"],
            "check_response_format": parameters["checkResponseFormat"],
        }

    def values(self, desired):
        return {
            "layer_id": desired["layer_id"],
            "info_format": _mime_type(desired["info_format"]),
            "i": desired["i"],
            "j": desired["j"],
            "feature_count": desired["feature_count"],
            "check_response_format": desired["check_response_format"],
        }

    def write(self, probe, desired):
        for name, value in self.values(desired).items():
            setattr(probe, name, value)
        probe.timeout = desired["timeout"]
        probe.save()


class WfsGetFeatureProbeSpec(ProbeSpec):
    """The bounded GetFeature probe of a feature type of a WFS.

    A response format is only requested when the service advertises one the
    probe can inspect; without a format the service answers its protocol
    default and the content checks stay at the exception level.
    """

    model = WebFeatureServiceGetFeatureProbe
    target_key = "targetFeatureType"
    parameters = frozenset({
        "featureTypes", "featureTypeIds", "crs", "crsId", "outputFormat",
        "outputFormatId", "maxFeatures", "timeout", "maxResponseBytes",
        "checkFeatureCollection", "expectFeatures"})

    def desired(self, probe_type, parameters, candidate):
        desired = {"timeout": self._timeout(parameters, candidate["parameters"])}
        target = self._element(
            parameters, candidate, ("featureTypes", "featureTypeIds"))
        proposed = candidate["parameters"]
        supported = candidate["supported"]

        crs = parameters.get("crs", proposed.get("crs"))
        if crs:
            crs = crs.upper()
            self._one_of(crs, "crs", {
                value.upper() for value in supported.get("crs", [])})
        output_format = parameters.get("outputFormat", proposed.get("outputFormat"))
        if output_format:
            self._one_of(output_format, "outputFormat",
                         supported.get("formats", []))

        bound = supported.get("maxFeatures") or MAX_FEATURES
        requested = _bounded_int(
            parameters.get("maxFeatures", proposed["maxFeatures"]),
            "maxFeatures", min(bound, MAX_FEATURES))
        count_bound = supported.get("countBound")
        if count_bound and requested > count_bound:
            # never ask a service for more features than it advertises to
            # answer by a single request
            raise ApplyError("parameters", 400, {
                "field": "maxFeatures", "expected": count_bound})

        desired.update({
            "feature_type_id": target["id"],
            "crs": crs,
            "output_format": output_format,
            "max_features": requested,
            "check_response_feature_collection": _boolean(
                parameters.get("checkFeatureCollection",
                               proposed["checkFeatureCollection"]),
                "checkFeatureCollection"),
            "check_response_contains_features": _boolean(
                parameters.get("expectFeatures",
                               proposed["expectFeatures"]),
                "expectFeatures"),
        })
        return desired

    def stored(self, probe):
        feature_types = list(
            probe.feature_types.values_list("identifier", "pk"))
        return {
            "timeout": probe.timeout,
            "feature_type_id": (str(feature_types[0][1])
                                if feature_types else None),
            "crs": (str(probe.reference_system).upper()
                    if probe.reference_system_id else None),
            "output_format": (str(probe.output_format)
                              if probe.output_format_id else None),
            "max_features": probe.max_features,
            "check_response_feature_collection":
                probe.check_response_feature_collection,
            "check_response_contains_features":
                probe.check_response_contains_features,
        }

    def regenerated(self, probe_type, parameters):
        return {
            "timeout": parameters.get("timeout"),
            "feature_type_id": str(parameters["featureTypeIds"][0]),
            "crs": (str(parameters["crs"]).upper()
                    if parameters.get("crs") else None),
            "output_format": parameters.get("outputFormat"),
            "max_features": parameters["maxFeatures"],
            "check_response_feature_collection":
                parameters["checkFeatureCollection"],
            "check_response_contains_features": parameters["expectFeatures"],
        }

    def relations(self, desired):
        return {"feature_types": [desired["feature_type_id"]]}

    def write(self, probe, desired):
        probe.timeout = desired["timeout"]
        probe.max_features = desired["max_features"]
        probe.reference_system = (
            _reference_system(desired["crs"]) if desired["crs"] else None)
        probe.output_format = (
            _mime_type(desired["output_format"])
            if desired["output_format"] else None)
        probe.check_response_feature_collection = \
            desired["check_response_feature_collection"]
        probe.check_response_contains_features = \
            desired["check_response_contains_features"]
        probe.save()
        for relation, ids in self.relations(desired).items():
            getattr(probe, relation).set(ids)

    def values(self, desired):
        return {
            "max_features": desired["max_features"],
            "reference_system": (
                _reference_system(desired["crs"]) if desired["crs"] else None),
            "output_format": (
                _mime_type(desired["output_format"])
                if desired["output_format"] else None),
            "check_response_feature_collection":
                desired["check_response_feature_collection"],
            "check_response_contains_features":
                desired["check_response_contains_features"],
        }


class DescribeFeatureTypeProbeSpec(ProbeSpec):
    """The comprehensive DescribeFeatureType probe of a feature type of a WFS."""

    model = WebFeatureServiceDescribeFeatureTypeProbe
    target_key = "targetFeatureType"
    parameters = frozenset({
        "featureTypes", "featureTypeIds", "outputFormat", "outputFormatId",
        "timeout", "maxResponseBytes"})

    def desired(self, probe_type, parameters, candidate):
        desired = {"timeout": self._timeout(parameters, candidate["parameters"])}
        target = self._element(
            parameters, candidate, ("featureTypes", "featureTypeIds"))
        proposed = candidate["parameters"]

        output_format = parameters.get("outputFormat", proposed.get("outputFormat"))
        if output_format:
            self._one_of(output_format, "outputFormat",
                         candidate["supported"].get("formats", []))

        desired.update({
            "feature_type_id": target["id"],
            "output_format": output_format,
        })
        return desired

    def stored(self, probe):
        feature_types = list(
            probe.feature_types.values_list("identifier", "pk"))
        return {
            "timeout": probe.timeout,
            "feature_type_id": (str(feature_types[0][1])
                                if feature_types else None),
            "output_format": (str(probe.output_format)
                              if probe.output_format_id else None),
        }

    def regenerated(self, probe_type, parameters):
        return {
            "timeout": parameters.get("timeout"),
            "feature_type_id": str(parameters["featureTypeIds"][0]),
            "output_format": parameters.get("outputFormat"),
        }

    def values(self, desired):
        return {
            "output_format": (
                _mime_type(desired["output_format"])
                if desired["output_format"] else None),
        }

    def relations(self, desired):
        return {"feature_types": [desired["feature_type_id"]]}

    def write(self, probe, desired):
        probe.timeout = desired["timeout"]
        probe.output_format = (
            _mime_type(desired["output_format"])
            if desired["output_format"] else None)
        probe.save()
        for relation, ids in self.relations(desired).items():
            getattr(probe, relation).set(ids)


def _polygon(bbox):
    polygon = Polygon.from_bbox(bbox)
    polygon.srid = 4326
    return polygon


#: the spec of every generatable probe type, keyed by service type and the OGC
#: operation the probe executes
PROBE_SPECS = {
    ("WMS", "GetCapabilities"): CapabilitiesProbeSpec(
        model=GetCapabilitiesProbe),
    ("WMS", "GetMap"): GetMapProbeSpec(),
    ("WMS", "GetFeatureInfo"): GetFeatureInfoProbeSpec(),
    ("WFS", "GetCapabilities"): CapabilitiesProbeSpec(
        model=WebFeatureServiceGetCapabilitiesProbe),
    ("WFS", "GetFeature"): WfsGetFeatureProbeSpec(),
    ("WFS", "DescribeFeatureType"): DescribeFeatureTypeProbeSpec(),
}

#: the concrete probe model of each generatable probe type, kept as the plain
#: mapping the report and the bounds read
PROBE_MODEL = {
    key: spec.model for key, spec in PROBE_SPECS.items()}

#: the preview parameter names one candidate of this probe type may carry
PARAMETER_NAMES = {
    key: set(spec.parameters) for key, spec in PROBE_SPECS.items()}


def setting_model(service):
    """The monitoring setting model of the service type of a service."""
    model = SETTING_MODEL.get(getattr(service, "service_type", None))
    if model is None:
        raise ApplyError("serviceType", 400)
    return model


def _service_type(service) -> str:
    return getattr(service, "service_type", None)


def _spec(service, probe_type) -> ProbeSpec:
    spec = PROBE_SPECS.get((_service_type(service), probe_type))
    if spec is None:
        raise ApplyError("probeType", 400, {"probeType": probe_type})
    return spec


def _models_of(service):
    """The probe models an apply can write for the service type."""
    return sorted({
        spec.model for (service_type, _type), spec in PROBE_SPECS.items()
        if service_type == _service_type(service)},
        key=lambda model: model._meta.label)


def _generated_probe_count(service):
    return sum(
        model.objects.filter(
            setting__service=service,
            origin=ProbeOriginEnum.GENERATED).count()
        for model in _models_of(service))


def _find_generated(model, identity):
    return model.objects.filter(
        origin=ProbeOriginEnum.GENERATED,
        generator_identity=identity).first()


def _create_probe(spec, service, setting, identity, preset, desired):
    """Create one generated probe; ``None`` when a concurrent apply won the race."""
    values = {
        "setting": setting,
        "origin": ProbeOriginEnum.GENERATED,
        "generator_version": GENERATOR_VERSION,
        "generator_preset": preset,
        "generator_identity": identity,
        "timeout": desired["timeout"],
    }
    values.update(spec.values(desired))
    relations = spec.relations(desired)
    try:
        with transaction.atomic():
            probe = spec.model(**values)
            probe.save()
            for relation, ids in relations.items():
                getattr(probe, relation).set(ids)
    except (IntegrityError, ValidationError, GDALException):
        # the unique constraint of the generator identity, or a lookup row
        # concurrently created: recognize the winner's row instead of failing
        return None
    return probe


def _apply_candidate(entry, service, setting, candidate, preset,
                     confirm_replace):
    """Persist one revalidated candidate and report what happened to it."""
    probe_type = candidate["probeType"]
    spec = _spec(service, probe_type)
    model = spec.model
    identity = generated_identity(
        service.pk, probe_type, spec.identities(candidate))
    desired = spec.validate(
        probe_type, entry.get("parameters") or {}, candidate)

    existing = _find_generated(model, identity)
    if existing is None:
        existing = _create_probe(
            spec, service, setting, identity, preset, desired)
        if existing is None:
            # a concurrent apply persisted the same candidate first
            existing = _find_generated(model, identity)
            if existing is None:
                raise ApplyError("stalePreview", 409, {
                    "candidates": [entry.get("candidateId")],
                    "reason": "the candidate vanished during the apply"})
        else:
            return {"candidateId": entry["candidateId"],
                    "probeType": probe_type, "action": "created",
                    "probeId": str(existing.pk)}

    stored = spec.stored(existing)
    current = spec.regenerated(probe_type, candidate["parameters"])
    if stored != current and not confirm_replace:
        return {"candidateId": entry["candidateId"],
                "probeType": probe_type, "action": "preserved",
                "probeId": str(existing.pk),
                "detail": "customized"}
    if stored == desired:
        action = "unchanged"
    else:
        spec.write(existing, desired)
        action = "updated"
    if existing.generator_preset != preset:
        # the identity keys on the target, not on the preset which proposed
        # it: a recognized probe carries the preset of the latest apply
        existing.generator_preset = preset
        existing.save()
    return {"candidateId": entry["candidateId"],
            "probeType": probe_type, "action": action,
            "probeId": str(existing.pk)}


def apply_generated_probes(service, payload) -> dict:
    """Persist the candidates an authorized user selected from a preview.

    Args:
        service: the registered service the preview was made for, a web map or
            a web feature service
        payload (dict): ``setting`` (id of the monitoring setting the probes
            belong to), ``probes`` (the selected candidates, each with
            ``candidateId``, ``probeType`` and the possibly user-edited
            ``parameters``), ``preset``, optional ``generatorVersion`` and
            ``confirmReplace``

    Returns:
        dict: the apply report (per candidate action and the summary)

    Raises:
        ApplyError: an invalid payload, a stale preview or an exceeded bound
        PreviewError: the service can not be generated from right now
    """
    if not isinstance(payload, dict):
        raise ApplyError("probes", 400)
    preset = str(payload.get("preset") or PRESET_STANDARD).strip().lower()
    if preset not in IMPLEMENTED_PRESETS:
        raise ApplyError("preset", 400)
    confirm_replace = payload.get("confirmReplace")
    if confirm_replace is not None and not isinstance(confirm_replace, bool):
        raise ApplyError("confirmReplace", 400)
    confirm_replace = bool(confirm_replace)

    model = setting_model(service)
    try:
        setting = model.objects.get(
            pk=payload.get("setting"), service=service)
    except (model.DoesNotExist, ValueError, TypeError, ValidationError):
        raise ApplyError("setting", 400)

    probes = payload.get("probes")
    if (not isinstance(probes, list) or not probes
            or not all(isinstance(entry, dict) and entry.get("candidateId")
                       and entry.get("probeType") for entry in probes)):
        raise ApplyError("probes", 400)
    if len(probes) > MAX_PROBES:
        raise ApplyError("limit", 400, {"bound": MAX_PROBES})
    candidate_ids = [entry["candidateId"] for entry in probes]
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ApplyError("probes", 400, {"reason": "duplicate candidateId"})
    unknown_type = [
        entry["probeType"] for entry in probes
        if (_service_type(service), entry["probeType"]) not in PROBE_SPECS]
    if unknown_type:
        raise ApplyError("probeType", 400, {"probeTypes": sorted(set(unknown_type))})

    generator_version = payload.get("generatorVersion")
    candidates = current_candidate_map(service)
    if generator_version is not None and str(generator_version) != GENERATOR_VERSION:
        raise ApplyError("stalePreview", 409, {
            "reason": "generatorVersion",
            "generatorVersion": GENERATOR_VERSION})

    stale = [
        entry["candidateId"] for entry in probes
        if entry["candidateId"] not in candidates
        or candidates[entry["candidateId"]]["probeType"] != entry["probeType"]]
    if stale:
        raise ApplyError("stalePreview", 409, {"candidates": stale})

    # the bound of generated probes the service may hold in total
    wanted_identities = {
        generated_identity(
            service.pk, entry["probeType"],
            _spec(service, entry["probeType"]).identities(
                candidates[entry["candidateId"]]))
        for entry in probes}
    already_generated = {
        identity
        for spec_model in _models_of(service)
        for identity in spec_model.objects.filter(
            origin=ProbeOriginEnum.GENERATED,
            generator_identity__in=wanted_identities).values_list(
                "generator_identity", flat=True)}
    if _generated_probe_count(service) + (
            len(wanted_identities) - len(already_generated)) > MAX_PROBES:
        raise ApplyError("limit", 400, {"bound": MAX_PROBES})

    results = []
    with transaction.atomic():
        for entry in probes:
            results.append(_apply_candidate(
                entry, service, setting, candidates[entry["candidateId"]],
                preset, confirm_replace))

    summary = {action: 0 for action in
               ("created", "updated", "unchanged", "preserved")}
    for result in results:
        summary[result["action"]] += 1
    return {
        "serviceId": str(service.pk),
        "settingId": str(setting.pk),
        "preset": preset,
        "generatorVersion": GENERATOR_VERSION,
        "confirmReplace": confirm_replace,
        "results": results,
        "summary": summary,
        "replaceConfirmationRequired": [
            result["candidateId"] for result in results
            if result.get("detail") == "customized"],
    }
