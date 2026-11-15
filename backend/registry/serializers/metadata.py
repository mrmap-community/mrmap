import re

from accounts.serializers.users import UserSerializer
from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext_lazy as _
from extras.serializers import (HistoryInformationSerializer,
                                StringRepresentationSerializer,
                                SystemInfoSerializerMixin)
from guardian.core import ObjectPermissionChecker
from registry.enums.metadata import MetadataOriginEnum
from registry.exceptions.metadata import PublishRefused
from registry.mappers.publish import (build_resulting_document,
                                      non_roundtrippable_fields,
                                      publish_document)
from registry.mappers.rules import (assessable_rule, evaluate_rules,
                                    findings_to_errors)
from registry.models.metadata import (ApplicationMetadataRecord, DatasetMetadataRecord,
                                      IsoCategory, Keyword, Language, Licence,
                                      MetadataContact, MetadataProfile,
                                      MetadataRelation, MimeType,
                                      ReferenceSystem, ServiceMetadataRecord,
                                      Style, TimeExtent)
from registry.models.service import CatalogueService, FeatureType, Layer
from rest_framework.fields import SerializerMethodField
from rest_framework.relations import (Hyperlink, HyperlinkedIdentityField)
from rest_framework_json_api.relations import ResourceRelatedField
from rest_framework_json_api.serializers import (ModelSerializer,
                                                 ValidationError)
from rest_framework_json_api.utils import undo_format_field_name

logger = settings.ROOT_LOGGER


class MimeTypeSerializer(
    StringRepresentationSerializer,
    SystemInfoSerializerMixin,
    ModelSerializer
):

    class Meta:
        model = MimeType
        fields = "__all__"


class KeywordSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:keyword-detail",
    )

    class Meta:
        model = Keyword
        fields = "__all__"


class LicenceSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:licence-detail",
    )

    class Meta:
        model = Licence
        fields = "__all__"


class ReferenceSystemDefaultSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:referencesystem-detail",
    )

    class Meta:
        model = ReferenceSystem
        fields = "__all__"


class ReferenceSystemRetrieveSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    wkt = SerializerMethodField()
    bbox = SerializerMethodField()
    is_xy_order = SerializerMethodField()
    is_yx_order = SerializerMethodField()

    url = HyperlinkedIdentityField(
        view_name="registry:referencesystem-detail",
    )

    class Meta:
        model = ReferenceSystem
        fields = "__all__"

    def get_wkt(self, obj):
        return obj.wkt

    def get_bbox(self, obj):
        if obj.extent:
            return obj.extent.envelope.geojson

    def get_is_xy_order(self, obj):
        return obj.is_xy_order

    def get_is_yx_order(self, obj):
        return obj.is_yx_order


class StyleSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(
        view_name="registry:style-detail",
    )

    class Meta:
        model = Style
        fields = "__all__"


class MetadataContactSerializer(
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:metadatacontact-detail")

    class Meta:
        model = MetadataContact
        fields = "__all__"


class TimeExtentSerializer(StringRepresentationSerializer, ModelSerializer):
    class Meta:
        model = TimeExtent
        fields = "__all__"


class LanguageSerializer(StringRepresentationSerializer, ModelSerializer):
    class Meta:
        model = Language
        fields = "__all__"


class IsoCategorySerializer(StringRepresentationSerializer, ModelSerializer):
    class Meta:
        model = IsoCategory
        fields = "__all__"


class MetadataProfileSerializer(StringRepresentationSerializer, ModelSerializer):
    """The authoring profile of the records (#1240), as a json:api resource.

    Sections and rules answer as plain attributes, so the editor fetches
    them with the record it edits (``include=profile``, optionally
    ``fields[profile]=rules``) and no frontend keeps a second copy of them.
    The ISO element paths of the fields are NOT here — they ride the
    OpenAPI schema, derived from the mapper configs (see registry/schema.py).
    """

    url = HyperlinkedIdentityField(view_name="registry:metadataprofile-detail")

    class Meta:
        model = MetadataProfile
        fields = "__all__"


class MetadataProfileRelatedField(ResourceRelatedField):
    """The ``profile`` relationship of a record, pointing at the profile itself.

    ``ResourceRelatedField`` builds its related link from the pk of the
    record which carries the relationship — its pattern is the nested
    routers' ``<parent>/<relation>/`` endpoint. A profile is no subresource
    of the record: the document the editor follows is the profile's own
    detail route, and the AC of #1240 say the record's profile link answers
    exactly that.
    """

    def get_links(self, obj=None, lookup_field="pk"):
        profile = getattr(obj, "profile", None) if obj is not None else None
        if profile is None:
            return {}
        request = self.context.get("request", None)
        url = self.reverse(
            "registry:metadataprofile-detail",
            kwargs={"pk": profile.pk},
            request=request,
        )
        return {"related": Hyperlink(url, "related")}


class MetadataRelationSerializer(ModelSerializer):
    included_serializers = {
        "layer": "registry.serializers.service.LayerSerializer",
        "feature_type": "registry.serializers.service.FeatureTypeSerializer",
        "wms": "registry.serializers.service.WebMapServiceSerializer",
        "wfs": "registry.serializers.service.WebFeatureServiceSerializer",
        "csw": "registry.serializers.service.CatalogueServiceSerializer",
    }

    class Meta:
        model = MetadataRelation
        fields = "__all__"


class RecordPermissionsSerializerMixin(HistoryInformationSerializer):
    can_edit = SerializerMethodField()
    can_delete = SerializerMethodField()

    def create(self, validated_data):
        """A record created without a profile is an iso19139-generic one.

        The api POST is the second creation path of a record besides the
        mapper persistence; both look the seeded profile up rather than
        naming it as a column default, see MetadataProfile.generic() (#1240).
        """
        if 'profile' not in validated_data:
            generic = MetadataProfile.generic()
            if generic is not None:
                validated_data['profile'] = generic
        return super().create(validated_data)

    def get_fields(self):
        fields = super().get_fields()
        if getattr(self.context.get("view"), "action", None) == "list":
            fields.pop("can_delete", None)
        return fields

    def _sparse_fieldset(self):
        """The field names the request asks for with ``fields[<Model>]``.

        Empty when the request names none. Same mechanism as
        ``ExplorerAttributesSerializer.explorer_fields`` of the services: a
        permission answer asserted per row is only paid for by the screen
        that reads it. (#1249: the batch edit needs ``canEdit`` of every
        record it was handed, to send only what the user may edit.)
        """
        request = self.context.get("request")
        if request is None:
            return []
        return [
            undo_format_field_name(name.strip())
            for name in request.GET.get(
                f"fields[{self.Meta.model.__name__}]", "").split(",")
            if name.strip()
        ]

    def to_representation(self, instance):
        result = super().to_representation(instance)
        if (getattr(self.context.get("view"), "action", None) == "list"
                and "can_edit" not in self._sparse_fieldset()):
            result.pop("can_edit", None)
        return result

    def _can_modify(self, obj, action):
        user = self.context["request"].user
        permission = f"{obj._meta.app_label}.{action}_{obj._meta.model_name}"
        if not user.has_perm(permission):
            return False
        request = self.context["request"]
        checker = getattr(request, "record_permission_checker", None)
        if checker is None:
            checker = ObjectPermissionChecker(user)
            request.record_permission_checker = checker
        return checker.has_perm(permission, obj)

    def get_can_edit(self, obj) -> bool:
        if (getattr(self.context.get("view"), "action", None) == "list"
                and "can_edit" not in self._sparse_fieldset()):
            # the value is popped from the list answer anyway (see
            # to_representation): assert it only for the list that asked
            return False
        return self._can_modify(obj, "change")

    def get_can_delete(self, obj) -> bool:
        return self._can_modify(obj, "delete")


def _member_form(name):
    """The comparison form of one json:api member or model field name.

    A payload may name a member in any casing or separator style the parser
    tolerated; the refusal names the field regardless of how it arrived.
    """
    return re.sub(r"[^0-9a-z]", "", name.lower())


class RecordWriteSerializerMixin:
    """The create/update semantics every metadata record endpoint answers (#1241).

    The endpoint itself is the default json:api CRUD behaviour of the shared
    ``ModelViewSet`` — POST/PUT/PATCH on the record resources, no bespoke
    action endpoints (the cross-cutting decision of the #1238 review). This
    mixin carries the rules which belong to a record write and to no
    other resource:

    * a write which names a field the model pins ``editable=False``
      (``file_identifier``, ``date_stamp``, ``origin``, ``is_broken``, … — the
      read-only pinning of #1240) is answered with a 400 naming every offending
      member through ``errors[].source.pointer``, instead of the silent
      dropping a ``read_only`` DRF field performs today;
    * a write which names a field the record's document is READ from but the
      write mapper can not WRITE (bounding geometry, time extents, the
      citation identifier) is refused with the same 400 naming the member —
      no enabled write may leave row, ``xml_backup_file`` and CSW output
      apart (readiness clarification of #1244);
    * the structural rules of the record's profile are asked as part of the
      normal CRUD request — the payload is validated on POST/PUT/PATCH, never
      through a separate call (§5 of the metadata-editor document). #1243
      supplies the rule content and the evaluator: PUT/PATCH run the profile's
      rules over the RESULTING ISO document — the record's stored document
      with the row's and payload's values written through the publish seam of
      #1244, in memory — and answer violations as json:api error objects
      citing the rule ids, before anything is stored. A record which serves no
      document yet (a POST, whose first document this save publishes at
      commit) has nothing for the document rules to govern at validation time;
      a rule set this version can not assess stays refused outright on every
      verb (fail-closed): an unevaluated rule set must never answer a payload
      as valid;
    * a record created through the api came from the editor: ``origin`` answers
      ``MetadataOriginEnum.EDITOR``, the value of a curator creation which the
      relation bookkeeping of #1245/#1261 already speaks. A created record
      carries the harvest gate's stamp the parsed date of an import would
      carry: ``date_stamp`` gets its creation default and the first editor
      update bumps it through the model save (see
      :meth:`registry.models.metadata.MetadataRecord.save`).

    The ISO 19139 document a record serves is regenerated by the publish seam
    of :mod:`registry.mappers.publish` — the one place allowed to turn model
    fields into the document (§5: no second interpretation layer). ``create``
    and ``update`` wrap their row save and :meth:`_publish_record` in one
    transaction (DRF opens none itself): a successful save is the publish
    (#1244) — fields, validation (#1243) and the document commit together or
    not at all, and a refused write changes nothing. Concurrency is
    last-write-wins (§7 decision 6): no lock is taken and no token answered;
    the last committed save serves.
    Whether a deployment opens these endpoints at all is the activation gate
    ``MRMAP_METADATA_EDITOR_WRITES_ENABLED`` (see
    :class:`registry.views.metadata.MetadataRecordWritesEnabled`), on by
    default since the round trip of this issue.
    """

    def validate(self, attrs):
        attrs = super().validate(attrs)
        self._reject_non_writable_members()
        self._reject_non_roundtrippable_members()
        self._validate_profile_rules(attrs)
        return attrs

    def create(self, validated_data):
        """The api POST is an editor's creation; the record says so afterwards.

        ``origin`` is ``editable=False`` on the model — the serializer can not
        be asked to write it and no payload may name it (see
        :meth:`_reject_non_writable_members`); the server stamps it here, where
        a server-assigned value belongs. The publish then generates the record's
        first document: a created record without one would fail the CSW page
        it appears in, so POST commits the skeleton-derived document together
        with the row (#1244).
        """
        validated_data["origin"] = MetadataOriginEnum.EDITOR.value
        with transaction.atomic():
            record = super().create(validated_data)
            return self._publish_record(record, validated_data)

    def update(self, instance, validated_data):
        """A successful PUT/PATCH is the publish of the edited record (#1244).

        The row save of ``super().update()`` set ``is_customized`` and bumped
        ``date_stamp`` (the harvest overwrite gate's side effects, #1241); the
        publish regenerates the served document from the SAVED row inside the
        same transaction, so the document carries the bumped stamp and a
        rollback leaves both at their previous state.
        """
        with transaction.atomic():
            record = super().update(instance, validated_data)
            return self._publish_record(record, validated_data)

    def _publish_record(self, record, validated_data):
        try:
            return publish_document(record, validated_data)
        except PublishRefused as refused:
            logger.error(
                "the publish of record %s was refused: %s",
                record.pk, refused)
            raise ValidationError(_(
                "The ISO document served for this record could not be "
                "regenerated from its stored fields; the write is refused "
                "so that the served document never disagrees with the "
                "record."))

    def _reject_non_writable_members(self):
        """Refuse a payload which names a field the model refuses to write.

        A DRF ``read_only`` field is dropped from the incoming data in silence;
        the json:api answer for such a write is a 400 which names the member
        (acceptance criteria of #1241). Which members those are is not a second
        list to maintain: every concrete model field with ``editable=False``
        which the serializer answers at all is read-only in the OpenAPI schema
        of #1240 and refused here — one derivation, one truth.
        """
        incoming = getattr(self, "initial_data", None)
        if not isinstance(incoming, dict):
            return
        # the primary key is the resource's identity: a json:api PATCH/PUT
        # names it in `data.id` by the spec, it is not a writable field the
        # payload is offered
        pk_name = self.Meta.model._meta.pk.name
        read_only = {
            field.name for field in self.Meta.model._meta.concrete_fields
            if not field.editable and field.name != pk_name
        } & set(self.get_fields().keys())
        forms = {_member_form(name): name for name in read_only}
        offenders = sorted({
            forms[_member_form(member)]
            for member in incoming
            if _member_form(member) in forms
        })
        if offenders:
            raise ValidationError({
                name: _("This field is read-only and can not be written.")
                for name in offenders
            })

    def _reject_non_roundtrippable_members(self):
        """Refuse a payload writing a field the document can not carry back.

        The readiness clarification of #1244 (2026-11-12): no enabled public
        write path may leave model fields, ``xml_backup_file`` and the CSW
        output out of sync. The fields the configs READ from the record's
        document but the write mapper of #1242 can not WRITE (bounding
        geometry, time extents, the citation identifier) would commit into the
        row while the served document silently kept its old value — the one
        sync gap a successful save could no longer heal. Refusing them is the
        same fail-closed posture as a rule set this version can not evaluate,
        and the set is derived from the configs (see
        :func:`registry.mappers.publish.non_roundtrippable_fields`), not kept
        as a second list.
        """
        incoming = getattr(self, "initial_data", None)
        if not isinstance(incoming, dict):
            return
        fields = self.get_fields()
        pk_name = self.Meta.model._meta.pk.name
        writable = {name for name, field in fields.items()
                    if name != pk_name and not field.read_only}
        refused = non_roundtrippable_fields(self.Meta.model, writable)
        forms = {_member_form(name): name for name in refused}
        offenders = sorted({
            forms[_member_form(member)]
            for member in incoming
            if _member_form(member) in forms
        })
        if offenders:
            raise ValidationError({
                name: _(
                    "This field is read out of the record's ISO document but "
                    "the document has no writable mapping for it; accepting "
                    "this write would leave the served document behind the "
                    "record.")
                for name in offenders
            })

    def _validate_profile_rules(self, attrs):
        """Run the profile's ISO rule set over the resulting document (#1243).

        The profile which governs the write is the one the payload names, the
        one the record under update carries, or the generic profile a created
        record falls back to (the creation paths of #1240). A rule set this
        version can not assess is refused on every verb (the fail-closed rule
        #1241 shipped and #1243 keeps for rule shapes it can not evaluate).
        On PUT/PATCH the rules run over the document the save WOULD produce:
        the record's stored document with the row's values, this payload
        included, written through the publish seam of #1244, in memory
        (readiness clarification: the same mapper semantics, never a
        disconnected representation). A record which serves no document yet
        (a POST, whose first document this very save generates at commit) has
        nothing for the document rules to govern at validation time — the
        posture #1243 shipped; it joins the rule regime with its next write,
        which evaluates the document its predecessor committed. Violations of
        `error` severity refuse the write with one json:api error object per
        finding, warnings ride along in that answer but never refuse alone —
        the document stays untouched either way, this runs before DRF saves
        anything.
        """
        profile = attrs.get("profile", None)
        if profile is None:
            profile = (self.instance.profile if self.instance is not None
                       else MetadataProfile.generic())
        rules = (profile.rules or []) if profile is not None else []
        if not rules:
            return
        if not all(assessable_rule(rule) for rule in rules):
            raise ValidationError(_(
                "The profile of this record names structural rules which this "
                "version can not evaluate; the write is refused instead of "
                "skipping the validation."
            ))
        if self.instance is None:
            # POST: no document is served for the created record until this
            # save publishes one at commit — nothing to validate over yet
            return
        document = self._resulting_document(attrs)
        if document is None:
            # the record carries no readable document yet: same posture as
            # POST — its first served document arrives with this save
            return
        findings = evaluate_rules(rules, document)
        if not any(f.severity == "error" for f in findings):
            # warnings never block a save; the editor rail shows them from
            # the rules it fetched with the record (#1245)
            return
        raise ValidationError({
            "non_field_errors": findings_to_errors(findings),
        })

    def _resulting_document(self, attrs):
        """The document bytes the save of this payload would produce.

        The one construction of the publish seam (see
        :func:`registry.mappers.publish.build_resulting_document`), in memory:
        what validation evaluates here is what the publish persists after the
        save — modulo the stamp the save itself bumps. Answers None for a
        record without a readable stored document; the write is refused
        fail-closed when the record can not be located in its own document or
        the write mapper refuses the combination: without an assessment the
        payload must not pass.
        """
        try:
            return build_resulting_document(
                self.instance, attrs, seed_missing=False)
        except PublishRefused:
            raise self._unassessable_document_error()

    @staticmethod
    def _unassessable_document_error():
        return ValidationError(_(
            "The structural rules of this record's profile could not be "
            "assessed against its ISO document; the write is refused "
            "instead of skipping the validation."
        ))


class DatasetMetadataRecordSerializer(
        RecordWriteSerializerMixin,
        RecordPermissionsSerializerMixin,
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:datasetmetadata-detail")

    profile = MetadataProfileRelatedField(
        queryset=MetadataProfile.objects,
        required=False,
        allow_null=True,
    )
    # POST of the minimal payload (profile + title + contact) creates a record
    # (#1241): only the contacts, which no column of the record may lack, stay
    # required - every other explicitly declared relation is optional to send,
    # the `blank=True`/`null=True` of its column, which an autogenerated
    # ModelSerializer field derives from the model and a declared one must say.
    self_pointing_layers = ResourceRelatedField(
        queryset=Layer.objects,
        many=True,
        required=False,
        related_link_view_name="registry:datasetmetadata-layers-list",
        related_link_url_kwarg="parent_lookup_metadata_relation__dataset_metadata",
    )
    self_pointing_feature_types = ResourceRelatedField(
        queryset=FeatureType.objects,
        many=True,
        required=False,
        related_link_view_name="registry:datasetmetadata-featuretypes-list",
        related_link_url_kwarg="parent_lookup_metadata_relation__dataset_metadata",
    )
    harvested_through = ResourceRelatedField(
        queryset=CatalogueService.objects,
        many=True,
        required=False,
        related_link_view_name="registry:datasetmetadata-csws-list",
        related_link_url_kwarg="parent_lookup_registry_datasetmetadatarecord_metadata_record",
    )
    dataset_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:datasetmetadata-datasetcontact-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord_dataset_contact'
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:datasetmetadata-metadatacontact-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord_metadata_contact'
    )
    licence = ResourceRelatedField(
        queryset=Licence.objects,
        required=False,
        related_link_view_name='registry:datasetmetadata-licence-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        required=False,
        related_link_view_name='registry:datasetmetadata-keywords-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord_metadata'
    )
    reference_systems = ResourceRelatedField(
        queryset=ReferenceSystem.objects,
        many=True,
        required=False,
        related_link_view_name='registry:datasetmetadata-referencesystems-list',
        related_link_url_kwarg='parent_lookup_datasetmetadatarecord'
    )

    included_serializers = {
        "self_pointing_layers": "registry.serializers.service.LayerSerializer",
        "self_pointing_feature_types": "registry.serializers.service.FeatureTypeSerializer",
        "harvested_through": "registry.serializers.service.CatalogueServiceSerializer",
        "dataset_contact": MetadataContactSerializer,
        "categories": IsoCategorySerializer,
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "licence": LicenceSerializer,
        "profile": MetadataProfileSerializer,
        "reference_systems": ReferenceSystemDefaultSerializer,
        "time_extents": TimeExtentSerializer,
        "languages": LanguageSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
    }

    class Meta:
        model = DatasetMetadataRecord
        # every field of the record but the vector: that is the index a search hits,
        # not a value an answer reads, and answered raw it is the text postgres
        # tokenized into, which no client can do anything with
        exclude = ("search_vector",)


class ServiceMetadataRecordSerializer(
        RecordWriteSerializerMixin,
        RecordPermissionsSerializerMixin,
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):

    url = HyperlinkedIdentityField(view_name="registry:servicemetadata-detail")

    profile = MetadataProfileRelatedField(
        queryset=MetadataProfile.objects,
        required=False,
        allow_null=True,
    )
    harvested_through = ResourceRelatedField(
        queryset=CatalogueService.objects,
        many=True,
        required=False,
        related_link_view_name="registry:servicemetadata-csws-list",
        related_link_url_kwarg="parent_lookup_registry_servicemetadatarecord_metadata_record",
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        # related_link_view_name='registry:servicemetadata-metadatacontact-list',
        related_link_url_kwarg='parent_lookup_servicemetadatarecord_metadata_contact'
    )
    licence = ResourceRelatedField(
        queryset=Licence.objects,
        required=False,
        # related_link_view_name='registry:servicemetadata-licence-list',
        related_link_url_kwarg='parent_lookup_servicemetadatarecord'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        required=False,
        # related_link_view_name='registry:servicemetadata-keywords-list',
        related_link_url_kwarg='parent_lookup_servicemetadatarecord_metadata'
    )
    reference_systems = ResourceRelatedField(
        queryset=ReferenceSystem.objects,
        many=True,
        required=False,
        related_link_view_name='registry:servicemetadata-referencesystems-list',
        related_link_url_kwarg='parent_lookup_servicemetadatarecord'
    )

    included_serializers = {
        "harvested_through": "registry.serializers.service.CatalogueServiceSerializer",
        "self_pointing_wms": "registry.serializers.service.WebMapServiceSerializer",
        "self_pointing_wfs": "registry.serializers.service.WebFeatureServiceSerializer",
        "self_pointing_csw": "registry.serializers.service.CatalogueServiceSerializer",
        "metadata_contact": MetadataContactSerializer,
        "keywords": KeywordSerializer,
        "licence": LicenceSerializer,
        "profile": MetadataProfileSerializer,
        "reference_systems": ReferenceSystemDefaultSerializer,
        "time_extents": TimeExtentSerializer,
        "languages": LanguageSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
    }

    class Meta:
        model = ServiceMetadataRecord
        # see DatasetMetadataRecordSerializer.Meta
        exclude = ("search_vector",)


class ApplicationMetadataRecordSerializer(
        RecordWriteSerializerMixin,
        RecordPermissionsSerializerMixin,
        StringRepresentationSerializer,
        SystemInfoSerializerMixin,
        ModelSerializer):
    """ The application record is shaped like the dataset record (#825), so its answer
    is the dataset answer without the self pointing resources and with the contact which
    provides the application in place of the one which provides the dataset.

    A list variant is not declared: like the dataset and the service record this single
    serializer answers both actions and ``RecordPermissionsSerializerMixin`` answers
    ``can_edit`` on the list only to a request that names it in the sparse fieldset
    (#1249), where it would otherwise be asserted per row.
    """

    url = HyperlinkedIdentityField(view_name="registry:applicationmetadata-detail")

    profile = MetadataProfileRelatedField(
        queryset=MetadataProfile.objects,
        required=False,
        allow_null=True,
    )
    harvested_through = ResourceRelatedField(
        queryset=CatalogueService.objects,
        many=True,
        required=False,
        related_link_view_name="registry:applicationmetadata-csws-list",
        related_link_url_kwarg="parent_lookup_registry_applicationmetadatarecord_metadata_record",
    )
    metadata_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:applicationmetadata-metadatacontact-list',
        related_link_url_kwarg='parent_lookup_applicationmetadatarecord_metadata_contact'
    )
    application_contact = ResourceRelatedField(
        queryset=MetadataContact.objects,
        related_link_view_name='registry:applicationmetadata-applicationcontact-list',
        related_link_url_kwarg='parent_lookup_applicationmetadatarecord_application_contact'
    )
    licence = ResourceRelatedField(
        queryset=Licence.objects,
        required=False,
        related_link_view_name='registry:applicationmetadata-licence-list',
        related_link_url_kwarg='parent_lookup_applicationmetadatarecord'
    )
    keywords = ResourceRelatedField(
        queryset=Keyword.objects,
        many=True,
        required=False,
        related_link_view_name='registry:applicationmetadata-keywords-list',
        related_link_url_kwarg='parent_lookup_applicationmetadatarecord_metadata'
    )
    reference_systems = ResourceRelatedField(
        queryset=ReferenceSystem.objects,
        many=True,
        required=False,
        related_link_view_name='registry:applicationmetadata-referencesystems-list',
        related_link_url_kwarg='parent_lookup_applicationmetadatarecord'
    )

    included_serializers = {
        "harvested_through": "registry.serializers.service.CatalogueServiceSerializer",
        "metadata_contact": MetadataContactSerializer,
        "application_contact": MetadataContactSerializer,
        "categories": IsoCategorySerializer,
        "keywords": KeywordSerializer,
        "licence": LicenceSerializer,
        "profile": MetadataProfileSerializer,
        "reference_systems": ReferenceSystemDefaultSerializer,
        "time_extents": TimeExtentSerializer,
        "languages": LanguageSerializer,
        "created_by": UserSerializer,
        "last_modified_by": UserSerializer,
    }

    class Meta:
        model = ApplicationMetadataRecord
        # see DatasetMetadataRecordSerializer.Meta
        exclude = ("search_vector",)
