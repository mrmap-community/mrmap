from collections import defaultdict
from importlib import import_module

from django.apps import apps
from django.db import models, transaction


class PersistenceHandler:
    def __init__(self, mapper):
        """
        mapper: XmlMapper-Instanz
        """
        self.mapper = mapper
        self.instances_by_model = self._build_instances_by_model()

    # ------------------------
    # Helper: load function
    # ------------------------
    @staticmethod
    def _load_function(path: str):
        mod_name, func_name = path.rsplit(".", 1)
        mod = import_module(mod_name)
        return getattr(mod, func_name)

    # ------------------------
    # Helper: Unique Fields
    # ------------------------
    @staticmethod
    def _get_unique_fields(_, model_cls):
        """Gibt die Unique-Feld-Kombinationen für das Modell zurück."""
        unique_sets = []

        for field in model_cls._meta.concrete_fields:
            if field.unique:
                unique_sets.append((field.name,))

        for constraint in getattr(model_cls._meta, "constraints", []):
            if isinstance(constraint, models.UniqueConstraint):
                unique_sets.append(tuple(constraint.fields))

        return unique_sets

    # ------------------------
    # Deduplicate & Bulk + Reload
    # ------------------------

    def _persist_get_or_create_bulk(self, model_cls, instances):
        if not instances:
            return {}

        # 1️⃣ Bestimme die relevanten Unique-Felder (ignoriere 'id')
        unique_sets = self._get_unique_fields(None, model_cls)
        key_fields = None
        for fields in unique_sets:
            if fields != ('id',):
                key_fields = fields
                break

        # fallback, falls kein anderes eindeutiges Feld existiert
        if key_fields is None:
            key_fields = ('id',)

        # 2️⃣ Deduplicate nach key_fields
        seen_keys = set()
        deduped_instances = []
        for inst in instances:
            key = tuple(getattr(inst, f) for f in key_fields)
            if key not in seen_keys:
                seen_keys.add(key)
                deduped_instances.append(inst)

        # 3️⃣ Prüfe, welche Objekte bereits in DB existieren
        filters = models.Q()
        for key in seen_keys:
            filters |= models.Q(**dict(zip(key_fields, key)))
        existing_objs = list(model_cls.objects.filter(filters))
        existing_keys = {tuple(getattr(e, f)
                               for f in key_fields): e for e in existing_objs}

        # 4️⃣ Objekte, die noch erstellt werden müssen
        to_create = [
            inst for inst in deduped_instances
            if tuple(getattr(inst, f) for f in key_fields) not in existing_keys
        ]
        if to_create:
            model_cls.objects.bulk_create(to_create, ignore_conflicts=True)

        # 5️⃣ Lade alle relevanten Objekte aus der DB
        # wir nutzen die unique-Felder, nicht PK
        final_objs = list(
            model_cls.objects.filter(
                models.Q(
                    **{f"{key_fields[0]}__in": [getattr(inst, key_fields[0]) for inst in deduped_instances]})
            )
        )
        final_key_map = {tuple(getattr(o, f)
                               for f in key_fields): o for o in final_objs}

        # Mapping von Key -> Originalinstanz für nächsten Schritt notwendig
        original_map = {
            tuple(getattr(inst, f) for f in key_fields): inst
            for inst in deduped_instances
        }

        # Nach Schritt 6: Füge private attributes zu den aus der db gezogenen neuen instanzen hinzu
        for key, final_obj in final_key_map.items():
            original_obj = original_map.get(key)
            if original_obj is not None:
                for attr, value in original_obj.__dict__.items():
                    if attr.endswith("_parsed") and not hasattr(final_obj, attr):
                        setattr(final_obj, attr, value)

        return final_key_map

    # ------------------------
    # Redirect M2M _parsed fields
    # ------------------------

    @staticmethod
    def _redirect_m2m_references(instances_by_model, final_instances_map):
        for model_cls, instances in instances_by_model.items():
            unique_sets = PersistenceHandler._get_unique_fields(
                None, model_cls)
            key_fields = unique_sets[0] if unique_sets else None
            for inst in instances:
                for attr_name in dir(inst):
                    if attr_name.startswith("_") and attr_name.endswith("_parsed"):
                        parsed = getattr(inst, attr_name)
                        if parsed is None:
                            continue
                        if isinstance(parsed, list):
                            new_list = []
                            for ref in parsed:
                                ref_map = final_instances_map.get(
                                    ref.__class__, {})
                                ref_key = tuple(
                                    getattr(ref, f) for f in key_fields) if key_fields else tuple()
                                final_obj = ref_map.get(ref_key)
                                if final_obj:
                                    new_list.append(final_obj)
                            setattr(inst, attr_name, new_list)
                        else:
                            ref_map = final_instances_map.get(
                                parsed.__class__, {})
                            ref_key = tuple(getattr(parsed, f)
                                            for f in key_fields) if key_fields else tuple()
                            final_obj = ref_map.get(ref_key)
                            if final_obj:
                                setattr(inst, attr_name, final_obj)

    # ------------------------
    # Build instances_by_model from XmlMapper
    # ------------------------
    def _build_instances_by_model(self):
        instances_by_model = defaultdict(
            lambda: {"instances": [], "_create_mode": "save"})
        cache = self.mapper.read_all_from_cache()

        for element_path, instance in cache.items():
            spec = self._find_spec_for_instance(self.mapper.mapping, instance)
            model_cls = type(instance)
            create_mode = spec.get("_create_mode", "save")
            entries = instances_by_model[model_cls]
            entries["instances"].append(instance)
            entries["_create_mode"] = create_mode

        # Flatten und attach _create_mode auf ModelClass
        flat_instances = {cls: data["instances"]
                          for cls, data in instances_by_model.items()}
        for cls, data in instances_by_model.items():
            setattr(cls, "_create_mode", data["_create_mode"])

        return flat_instances

    @staticmethod
    def _find_spec_for_instance(specs: dict, instance):
        """Sucht rekursiv das Spec für eine Instanz."""
        for key, value in specs.items():
            if not isinstance(value, dict):
                continue
            model_label = value.get("_model")
            if model_label:
                model_cls = apps.get_model(model_label)
                if isinstance(instance, model_cls):
                    return value
            # rekursiv
            for field_spec in value.get("fields", {}).values():
                if isinstance(field_spec, dict) and "_model" in field_spec:
                    found = PersistenceHandler._find_spec_for_instance(
                        {key: field_spec}, instance)
                    if found:
                        return found
        return {}

    # ------------------------
    # Run _pre_save hook
    # ------------------------
    def _run_pre_save_hook(self):
        pre_save_func_path = self.mapper.mapping.get("_pre_save")
        if not pre_save_func_path:
            return
        pre_save_func = self._load_function(pre_save_func_path)
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

    # ------------------------
    # Redirect FK and M2M _parsed fields
    # ------------------------

    def _apply_foreign_keys(self, instances_by_model, final_instances_map):
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
                        ref_map = final_instances_map.get(fk_type, {})

                        # Unique-Felder bestimmen, id ignorieren
                        unique_sets = [s for s in PersistenceHandler._get_unique_fields(
                            None, fk_type) if s != ('id',)]
                        key_fields = unique_sets[0] if unique_sets else None
                        if key_fields:
                            try:
                                ref_key = tuple(getattr(fk_obj, kf)
                                                for kf in key_fields)
                            except AttributeError:
                                continue  # Feld nicht gesetzt
                            final_obj = ref_map.get(ref_key)
                            if final_obj:
                                setattr(inst, f.name, final_obj)

    def _apply_parsed_m2m(self, final_instances_map):
        # -----------------------
        # ManyToMany (_parsed)
        # -----------------------
        for model_cls, instances in self.instances_by_model.items():
            for inst in instances:
                for field in model_cls._meta.local_many_to_many:
                    parsed_instances_attr = f"_{field.name}_parsed"
                    parsed = getattr(inst, parsed_instances_attr) if hasattr(
                        inst, parsed_instances_attr) else None
                    if parsed is None:
                        continue

                    final_list = []
                    for ref in parsed:
                        ref_map = final_instances_map.get(type(ref), {})
                        unique_sets = [s for s in PersistenceHandler._get_unique_fields(
                            None, type(ref)) if s != ('id',)]
                        key_fields = unique_sets[0] if unique_sets else None
                        if key_fields:
                            try:
                                ref_key = tuple(getattr(ref, kf)
                                                for kf in key_fields)
                            except AttributeError:
                                continue
                            final_obj = ref_map.get(ref_key)
                            if final_obj:
                                final_list.append(final_obj)

                    getattr(inst, field.name).set(final_list)

    # ------------------------
    # Persist all
    # ------------------------
    @transaction.atomic
    def persist_all(self):
        # 1️⃣ Pre-save Hook
        self._run_pre_save_hook()

        final_instances_map = {}

        # 2️⃣ Alle Models nach Abhängigkeiten sortieren
        sorted_models = self._sort_models_by_dependencies()

        # 3️⃣ Objekte speichern
        for model_cls in sorted_models:
            instances = self.instances_by_model.get(model_cls, [])
            if not instances:
                continue

            create_mode = getattr(model_cls, "_create_mode", "save")

            if create_mode == "get_or_create":
                final_key_map = self._persist_get_or_create_bulk(
                    model_cls, instances)
                self.instances_by_model[model_cls] = list(
                    final_key_map.values())
                final_instances_map[model_cls] = final_key_map
            elif create_mode == "bulk":
                # FK fields aktualisieren mit bereits gespeicherten instanzen
                self._apply_foreign_keys(
                    {model_cls: instances}, final_instances_map)
                # TODO: the instances which we are creating in bulk, shoul also be part of final_instances_map.
                # If not it is not safe way. Maybe any other instance would reference one of the created instances.
                model_cls.objects.bulk_create(instances)
            else:  # default save every instance
                # FK fields aktualisieren mit bereits gespeicherten instanzen
                self._apply_foreign_keys(
                    {model_cls: instances}, final_instances_map)
                for inst in instances:
                    # TODO: same as for bulk_create. The instance which will be saved here, becomes a safe pk and should become part of final_instances.
                    inst.save()

        # 4️⃣ Jetzt alle M2M-Felder aus _parsed setzen
        self._apply_parsed_m2m(final_instances_map)
