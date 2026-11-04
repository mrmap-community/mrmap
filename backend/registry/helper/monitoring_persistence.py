"""Idempotent persistence of selected monitoring probe preview candidates.

The apply action of the monitoring epic consumes the candidates of the preview
endpoint of #742. This module is the server side of that hand-off:

* **Revalidation against the CURRENT capabilities.** Every submitted candidate
  is re-identified against ``current_candidate_map`` of
  ``registry.helper.monitoring_generation``; a candidate an outdated preview
  proposed for capabilities which changed since (the layer is gone,
  deactivated, no longer renderable...) is refused with ``stalePreview`` and
  the client is asked for a fresh preview. The submitted parameters are
  validated against the CURRENT proposal — the preview passthrough is never
  trusted: CRS and format must be advertised for the layer, image dimensions
  and timeouts must stay inside the generator bounds, and the layer of a
  candidate can not be swapped for another one.
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
  candidate identity — e.g. an updated layer extent — are indistinguishable
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
* **Bounds.** At most ``MAX_PROBES`` candidates per apply, and a service
  holds at most ``MAX_PROBES`` generated probes in total; the execution side
  of the bound is the chunked dispatch of ``registry.tasks.monitoring``.
"""
from django.contrib.gis.gdal import GDALException
from django.contrib.gis.geos import Polygon
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from registry.enums.monitoring import ProbeOriginEnum
from registry.helper.monitoring_generation import (
    GENERATOR_VERSION, IMPLEMENTED_PRESETS, MAX_IMAGE_DIMENSION, MAX_PROBES,
    MAX_TIMEOUT, PRESET_STANDARD, current_candidate_map, generated_identity)
from registry.models.metadata import MimeType, ReferenceSystem
from registry.models.monitoring import (GetCapabilitiesProbe, GetMapProbe,
                                        WebMapServiceMonitoringSetting)

#: the preview parameter names one candidate of this probe type may carry;
#: a name outside the whitelist is refused instead of being ignored silently
PARAMETER_NAMES = {
    "GetCapabilities": {"timeout", "maxResponseBytes"},
    "GetMap": {
        "layers", "layerIds", "styles", "crs", "crsId", "format", "formatId",
        "bbox", "requestBbox", "axisOrder", "width", "height", "timeout",
        "maxResponseBytes", "exceptions", "dimensionDefaults", "time",
        "elevation"},
}

#: the concrete probe model of each generatable probe type
PROBE_MODEL = {
    "GetCapabilities": GetCapabilitiesProbe,
    "GetMap": GetMapProbe,
}

WORLD_EXTENT = (-180.0, -90.0, 180.0, 90.0)


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


def _persisted_from_submission(probe_type, parameters, candidate):
    """The validated, persistable subset of one submitted candidate.

    Values the probe model does not store (styles, exceptions, dimension
    defaults, the serialized request bbox) are validated against the current
    proposal where they can be, but never written: the executing probe
    derives them from the stored layer and CRS state anyway.
    """
    if not isinstance(parameters, dict):
        raise ApplyError("parameters", 400, {"field": "parameters"})
    unknown = set(parameters) - PARAMETER_NAMES[probe_type]
    if unknown:
        raise ApplyError("parameters", 400, {
            "field": "parameters", "unknown": sorted(unknown)})
    proposed = candidate["parameters"]
    validated = {}

    timeout = parameters.get("timeout", proposed.get("timeout"))
    validated["timeout"] = _bounded_int(
        timeout, "timeout", MAX_TIMEOUT)

    if probe_type == "GetCapabilities":
        return validated

    target = candidate["targetLayer"]
    for name in ("layers", "layerIds"):
        if name in parameters:
            value = parameters.get(name)
            expected = ([target["identifier"]] if name == "layers"
                        else [str(target["id"])])
            if list(value or []) != expected:
                # the stable identity binds the candidate to its layer; a
                # submitted edit can never silently re-point the probe
                raise ApplyError("parameters", 400, {
                    "field": name, "expected": expected})

    crs = (parameters.get("crs") or proposed["crs"]).upper()
    advertised = {value.upper() for value in candidate["supported"]["crs"]}
    if advertised and crs not in advertised:
        raise ApplyError("parameters", 400, {
            "field": "crs", "expected": sorted(advertised)})
    image_format = parameters.get("format") or proposed["format"]
    formats = candidate["supported"]["formats"]
    if formats and image_format not in formats:
        raise ApplyError("parameters", 400, {
            "field": "format", "expected": formats})

    validated["crs"] = crs
    validated["format"] = image_format
    validated["layer_id"] = target["id"]
    validated["width"] = _bounded_int(
        parameters.get("width", proposed["width"]), "width",
        MAX_IMAGE_DIMENSION)
    validated["height"] = _bounded_int(
        parameters.get("height", proposed["height"]), "height",
        MAX_IMAGE_DIMENSION)
    validated["bbox"] = _bbox(parameters.get("bbox", proposed["bbox"]))
    return validated


def _persisted_of_probe(probe):
    """The stored parameters of a probe in the shape of ``_persisted_from_submission``."""
    persisted = {"timeout": probe.timeout}
    if isinstance(probe, GetMapProbe):
        layers = list(probe.layers.values_list("identifier", "pk"))
        polygon = probe.bbox_lat_lon
        persisted.update({
            "crs": (str(probe.reference_system).upper()
                    if probe.reference_system_id else None),
            "format": str(probe.format) if probe.format_id else None,
            "layer_id": str(layers[0][1]) if layers else None,
            "width": probe.width,
            "height": probe.height,
            "bbox": _bbox(polygon.extent) if polygon is not None else None,
        })
    return persisted


def _persisted_of_proposal(probe_type, parameters):
    """The regeneration parameters in the shape of ``_persisted_of_probe``."""
    if probe_type == "GetCapabilities":
        return {"timeout": parameters.get("timeout")}
    return {
        "timeout": parameters.get("timeout"),
        "crs": str(parameters.get("crs")).upper(),
        "format": parameters.get("format"),
        "layer_id": str(parameters["layerIds"][0]),
        "width": parameters.get("width"),
        "height": parameters.get("height"),
        "bbox": _bbox(parameters["bbox"]),
    }


def _write_probe(probe, desired):
    """Write validated parameters onto a probe row (never its setting)."""
    probe.timeout = desired["timeout"]
    if isinstance(probe, GetMapProbe):
        probe.width = desired["width"]
        probe.height = desired["height"]
        probe.reference_system = _reference_system(desired["crs"])
        probe.format = _mime_type(desired["format"])
        probe.bbox_lat_lon = Polygon.from_bbox(desired["bbox"])
        probe.bbox_lat_lon.srid = 4326
        probe.save()
        probe.layers.set([desired["layer_id"]])
    else:
        probe.save()


def _create_probe(model, service, setting, identity, preset, desired):
    """Create one generated probe; ``None`` when a concurrent apply won the race."""
    values = {
        "setting": setting,
        "origin": ProbeOriginEnum.GENERATED,
        "generator_version": GENERATOR_VERSION,
        "generator_preset": preset,
        "generator_identity": identity,
        "timeout": desired["timeout"],
    }
    try:
        with transaction.atomic():
            probe = model(**values)
            if model is GetMapProbe:
                probe.width = desired["width"]
                probe.height = desired["height"]
                probe.reference_system = _reference_system(desired["crs"])
                probe.format = _mime_type(desired["format"])
                probe.bbox_lat_lon = Polygon.from_bbox(desired["bbox"])
                probe.bbox_lat_lon.srid = 4326
            probe.save()
            if model is GetMapProbe:
                probe.layers.set([desired["layer_id"]])
    except (IntegrityError, ValidationError, GDALException):
        # the unique constraint of the generator identity, or a lookup row
        # concurrently created: recognize the winner's row instead of failing
        return None
    return probe


def _generated_probe_count(service):
    return sum(
        model.objects.filter(
            setting__service=service,
            origin=ProbeOriginEnum.GENERATED).count()
        for model in PROBE_MODEL.values())


def _find_generated(model, identity):
    return model.objects.filter(
        origin=ProbeOriginEnum.GENERATED,
        generator_identity=identity).first()


def _apply_candidate(entry, service, setting, candidate, preset,
                     confirm_replace):
    """Persist one revalidated candidate and report what happened to it."""
    probe_type = candidate["probeType"]
    model = PROBE_MODEL[probe_type]
    target = candidate["targetLayer"]
    identity = generated_identity(
        service.pk, probe_type,
        [target["identifier"]] if target else [])
    desired = _persisted_from_submission(
        probe_type, entry.get("parameters") or {}, candidate)

    existing = _find_generated(model, identity)
    if existing is None:
        existing = _create_probe(
            model, service, setting, identity, preset, desired)
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

    stored = _persisted_of_probe(existing)
    current = _persisted_of_proposal(probe_type, candidate["parameters"])
    if stored != current and not confirm_replace:
        return {"candidateId": entry["candidateId"],
                "probeType": probe_type, "action": "preserved",
                "probeId": str(existing.pk),
                "detail": "customized"}
    if stored == desired:
        action = "unchanged"
    else:
        _write_probe(existing, desired)
        action = "updated"
    return {"candidateId": entry["candidateId"],
            "probeType": probe_type, "action": action,
            "probeId": str(existing.pk)}


def apply_generated_probes(service, payload) -> dict:
    """Persist the candidates an authorized user selected from a preview.

    Args:
        service (WebMapService): the registered service the preview was made for
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

    try:
        setting_pk = payload.get("setting")
        setting = WebMapServiceMonitoringSetting.objects.get(
            pk=setting_pk, service=service)
    except (WebMapServiceMonitoringSetting.DoesNotExist, ValueError,
            TypeError, ValidationError):
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
            [candidates[entry["candidateId"]]["targetLayer"]["identifier"]]
            if candidates[entry["candidateId"]]["targetLayer"] else [])
        for entry in probes}
    already_generated = {
        identity
        for model in PROBE_MODEL.values()
        for identity in model.objects.filter(
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
