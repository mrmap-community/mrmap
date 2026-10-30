from collections import defaultdict
from importlib import import_module
from logging import Logger

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import models, transaction
from lxml import etree
from registry.mappers.utils import (find_spec_for_instance, get_key_fields,
                                    get_unique_fields, make_instance_key,
                                    sort_key_for_instance)
from registry.models.document import DocumentModelMixin
from simple_history.utils import bulk_create_with_history

logger: Logger = settings.ROOT_LOGGER


class PersistenceHandler:
    def __init__(self, mapper, defaults={}):
        """
        mapper: XmlMapper-Instanz
        """
        self.mapper = mapper
        # FIXME: self.defaults is never accessed. Implement default handling
        self.defaults = defaults
        self.final_instances_map = {}

    # ------------------------
    # Helper: load function
    # ------------------------

    @staticmethod
    def _load_function(path: str):
        mod_name, func_name = path.rsplit(".", 1)
        mod = import_module(mod_name)
        return getattr(mod, func_name)

    # ------------------------
    # Get or create on the shared lookup tables
    # ------------------------

    def _persist_get_or_create(self, instances):
        """Persists all instances of one model, keyed by their unique key.

        This mode writes the shared lookup tables: Keyword, ReferenceSystem,
        MetadataContact, TimeExtent, ... Harvest workers import their metadata
        files concurrently and every one of them creates the rows its document
        carries. Looking each row up and inserting it on its own, in the order
        the document happens to carry them, makes two transactions wait for each
        other's entry in the same unique index in opposite order. Postgres ends
        that cycle by rolling back the whole import transaction of one of them
        (#817), which the retry on OperationalError of the harvesting task only
        hides.

        Therefore: deduplicate the parsed instances, insert them with one
        statement in key order - transactions which all ask for their rows in
        the same order can not wait for each other in a circle - and with
        ON CONFLICT DO NOTHING, because a row a concurrent transaction created
        since we last looked is the normal outcome and not an error. The stored
        ids come back with the final key map.
        """
        if not instances:
            return {}
        model_cls = instances[0].__class__
        key_fields = get_key_fields(model_cls)
        if key_fields == ('id',):
            # without a unique field there is nothing to deduplicate, to order
            # by or to insert conflict free
            return self._persist_get_or_create_one_by_one(instances, key_fields)

        deduped_instances = {}
        for inst in instances:
            self._fill_unique_defaults(inst, key_fields)
            deduped_instances.setdefault(
                make_instance_key(inst, key_fields), inst)

        to_create = sorted(
            deduped_instances.values(),
            key=lambda inst: sort_key_for_instance(inst, key_fields))
        model_cls.objects.bulk_create(
            objs=to_create, ignore_conflicts=True)

        return self.build_final_key_map(list(deduped_instances.values()), key_fields)

    def _persist_get_or_create_one_by_one(self, instances, key_fields):
        """Looks every instance up and creates it if it was not found.

        The fallback for a model without a unique field, which the bulk insert
        of _persist_get_or_create can not deduplicate, order or conflict on.
        """
        model_cls = instances[0].__class__
        db_instances = []
        for inst in instances:
            obj, created = model_cls.objects.get_or_create(
                **{f: getattr(inst, f) for f in key_fields},
                defaults={f.name: getattr(
                    inst, f.name) for f in model_cls._meta.fields if f.name not in key_fields}
            )
            db_instances.append(obj)
        return self.build_final_key_map(db_instances, key_fields)

    @staticmethod
    def _fill_unique_defaults(instance, key_fields):
        """Uses the field default for a unique field the parser left out.

        The columns of the unique constraints of the lookup tables are never
        null and carry a default, so the row which is identified by them stores
        the default and not NULL. `UniqueConstraintDefaultValueManager` applies
        this rule to the lookup of a single row already; deduplicating the
        parsed instances and inserting them in bulk needs the same value on the
        instance to ask for the same row.
        """
        for name in key_fields:
            field = instance._meta.get_field(name)
            if getattr(instance, name) is None and not field.null:
                setattr(instance, name, field.get_default())

    def build_final_key_map(self, instances, key_fields=None):
        model_cls = instances[0].__class__
        if not key_fields:
            key_fields = get_key_fields(model_cls)
        # 5️⃣ Lade alle relevanten Objekte aus der DB
        # wir nutzen die unique-Felder, nicht PK
        filters = models.Q()
        for inst in instances:
            filters |= models.Q(**{
                k: getattr(inst, k) for k in key_fields
            })

        final_objs = model_cls.objects.filter(filters)

        final_key_map = {
            make_instance_key(o, key_fields): o for o in final_objs
        }

        original_map = {
            make_instance_key(inst, key_fields): inst for inst in instances
        }

        self.inject_private_attributes(final_key_map, original_map)

        return final_key_map

    def inject_private_attributes(self, final_objects, original_objects):
        # Nach Schritt 6: Füge private attributes zu den aus der db gezogenen neuen instanzen hinzu
        for key, final_obj in final_objects.items():
            original_obj = original_objects.get(key)
            if original_obj is not None:
                for attr, value in original_obj.__dict__.items():
                    if (attr.endswith("_parsed") or attr.endswith('_custom_state')) and not hasattr(final_obj, attr):
                        setattr(final_obj, attr, value)

    # ------------------------
    # Build instances_by_model from XmlMapper
    # ------------------------
    def _build_instances_by_model(self):
        instances_by_model = defaultdict(
            lambda: {"instances": [], "_create_mode": "save"})
        cache = self.mapper.read_all_from_cache()

        for element_path, instance in cache.items():
            if not instance:
                logger.warning(f"elemt '{element_path}' is None")
                continue

            spec = find_spec_for_instance(self.mapper.mapping, instance)
            model_cls = type(instance)
            create_mode = spec.get("_create_mode", "save")
            entries = instances_by_model[model_cls]
            entries["instances"].append(instance)
            entries["_create_mode"] = create_mode

        # Flatten und attach _create_mode auf ModelClass
        flat_instances = {cls: data["instances"]
                          for cls, data in instances_by_model.items()}
        for inst, data in instances_by_model.items():
            setattr(inst, "_create_mode", data["_create_mode"])

        return flat_instances

    # ------------------------
    # Run _pre_save hook
    # ------------------------
    def _run_pre_save_hook(self):
        pre_save = self.mapper.mapping.get("_pre_save")
        if not pre_save:
            return

        # Wenn nur ein einzelner Funktionspfad angegeben wurde → in Liste packen
        if isinstance(pre_save, (list, tuple)):
            hooks = pre_save
        else:
            hooks = (pre_save,)

        for func_path in hooks:
            pre_save_func = self._load_function(func_path)
            pre_save_func(self.mapper)

    # ------------------------
    # Sort models by FK dependencies
    # ------------------------
    def _sort_models_by_dependencies(self):
        models_to_sort = set(self.instances_by_model.keys())

        model_deps = {m: set() for m in models_to_sort}
        reverse_deps = {m: set() for m in models_to_sort}

        for model_cls in models_to_sort:
            for f in model_cls._meta.concrete_fields:
                if isinstance(f, models.ForeignKey):
                    remote_model = f.remote_field.model
                    # Self-FK ignorieren
                    if remote_model in models_to_sort and remote_model != model_cls:
                        model_deps[model_cls].add(remote_model)
                        reverse_deps[remote_model].add(model_cls)

        sorted_models = []
        no_deps = [m for m, deps in model_deps.items() if not deps]

        while no_deps:
            m = no_deps.pop(0)
            sorted_models.append(m)

            for dependent in reverse_deps[m]:
                model_deps[dependent].remove(m)
                if not model_deps[dependent]:
                    no_deps.append(dependent)

        # Zyklische Abhängigkeiten (falls vorhanden) hinten anhängen
        remaining = [m for m, deps in model_deps.items() if deps]
        sorted_models.extend(remaining)

        return sorted_models

    def _inject_defaults(self, instances_by_model):
        for model_cls, instances in instances_by_model.items():
            defaults = self.defaults.get(model_cls.__name__, {})
            if not defaults:
                continue

            for inst in instances:
                for field_name, value in defaults.items():
                    current_value = getattr(inst, field_name)
                    if not current_value:
                        setattr(inst, field_name, value)

    # ------------------------
    # Redirect FK and M2M _parsed fields
    # ------------------------
    def _apply_foreign_keys(self, instances_by_model):
        """
        Setzt alle ForeignKey- und ManyToMany-Felder auf die final gespeicherten Objekte,
        die zuvor als _parsed referenziert wurden oder als mutable Objekte vorliegen.
        Ignoriert 'id' als eindeutiges Feld, wenn das Objekt noch nicht gespeichert ist.
        """
        for model_cls, instances in instances_by_model.items():
            for inst in instances:
                # -----------------------
                # ForeignKeys
                # -----------------------
                for f in model_cls._meta.concrete_fields:
                    if isinstance(f, models.ForeignKey):
                        fk_obj = getattr(inst, f.name, None)
                        if fk_obj is None:
                            continue

                        fk_type = f.remote_field.model
                        ref_map = self.final_instances_map.get(fk_type, {})

                        # Unique-Felder bestimmen, id ignorieren
                        unique_sets = [s for s in get_unique_fields(
                            fk_type) if s != ('id',)]
                        key_fields = unique_sets[0] if unique_sets else None
                        if key_fields:
                            try:
                                ref_key = make_instance_key(
                                    fk_obj, key_fields)
                            except AttributeError:
                                continue  # Feld nicht gesetzt
                            final_obj = ref_map.get(ref_key)
                            if final_obj:
                                setattr(inst, f.name, final_obj)

    def _apply_parsed_m2m(self):
        # -----------------------
        # ManyToMany (_parsed)
        # -----------------------
        for model_cls, instances in self.instances_by_model.items():
            # Get the mapping of original instances to final persisted instances
            final_instance_map = self.final_instances_map.get(model_cls, {})
            key_fields = get_key_fields(model_cls)

            for inst in instances:
                # Look up the final persisted instance
                inst_key = make_instance_key(inst, key_fields)
                final_inst = final_instance_map.get(inst_key)

                if not final_inst:
                    # Fallback: if not found by key, skip M2M for this instance
                    continue

                for field in model_cls._meta.local_many_to_many:
                    parsed_instances_attr = f"_{field.name}_parsed"
                    parsed = getattr(inst, parsed_instances_attr) if hasattr(
                        inst, parsed_instances_attr) else None
                    if parsed is None:
                        continue

                    final_list = []
                    for ref in parsed:
                        ref_map = self.final_instances_map.get(type(ref), {})
                        unique_sets = [s for s in get_unique_fields(
                            type(ref)) if s != ('id',)]
                        key_fields_ref = unique_sets[0] if unique_sets else None
                        if key_fields_ref:
                            try:
                                ref_key = make_instance_key(
                                    ref, key_fields_ref)
                            except AttributeError:
                                continue
                            final_obj = ref_map.get(ref_key)
                            if final_obj:
                                final_list.append(final_obj)

                    # Use the final_inst (which is persisted in DB) to set M2M relationships
                    getattr(final_inst, field.name).set(final_list)

    def _save_xml_backup_file(self, instance: models.Model):
        if not isinstance(instance, DocumentModelMixin):
            return
        if xml_str := getattr(self.mapper, "xml_str", None):
            content = xml_str
        else:
            content = etree.tostring(
                self.mapper.xml_root.getroottree(), encoding="utf-8", pretty_print=True)
        # calling save() on a FileField will also save the model instance
        instance.xml_backup_file.save(
            "backup.xml", content=ContentFile(content))

    def prepare_for_persist(self):
        self._run_pre_save_hook()
        self.instances_by_model = self._build_instances_by_model()

    # ------------------------
    # Persist all
    # ------------------------
    @transaction.atomic
    def persist_all(self):
        # 1️⃣ Pre-save Hook
        self.prepare_for_persist()

        # 2️⃣ Alle Models nach Abhängigkeiten sortieren
        sorted_models = self._sort_models_by_dependencies()

        # 3️⃣ Objekte speichern
        for model_cls in sorted_models:
            instances = self.instances_by_model.get(model_cls, [])
            if not instances:
                continue
            # FK fields aktualisieren mit bereits gespeicherten instanzen
            self._apply_foreign_keys(
                {model_cls: instances})

            self._inject_defaults(
                {model_cls: instances})

            create_mode = getattr(model_cls, "_create_mode", "save")
            kwargs = {}
            if "." in create_mode:
                create_func = self._load_function(create_mode)
                kwargs = {"handler": self}
                final_key_map = create_func(instances, **kwargs)
                self.final_instances_map[model_cls] = final_key_map
            elif create_mode == "get_or_create":
                final_key_map = self._persist_get_or_create(instances)
                self.final_instances_map[model_cls] = final_key_map
            elif create_mode == "bulk":
                objs = model_cls.objects.bulk_create(instances)
                final_key_map = self.build_final_key_map(objs)
                self.final_instances_map[model_cls] = final_key_map
            elif create_mode == "bulk_with_history":
                objs = bulk_create_with_history(instances, model_cls)
                final_key_map = self.build_final_key_map(objs)
                self.final_instances_map[model_cls] = final_key_map
            else:  # default save every instance
                for inst in instances:
                    inst.save()
                    if isinstance(inst, DocumentModelMixin):
                        self._save_xml_backup_file(inst)
                final_key_map = self.build_final_key_map(instances)
                self.final_instances_map[model_cls] = final_key_map

        # 4️⃣ Jetzt alle M2M-Felder aus _parsed setzen
        self._apply_parsed_m2m()
        return self.final_instances_map
