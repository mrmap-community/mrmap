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
    @transaction.atomic
    def _persist_get_or_create_bulk(self, model_cls, instances):
        if not instances:
            return {}

        unique_sets = self._get_unique_fields(None, model_cls)
        if not unique_sets:
            # Kein eindeutiges Feld → bulk_create alles
            model_cls.objects.bulk_create(instances)
            return {tuple(): inst for inst in instances}

        key_fields = unique_sets[0]
        seen_keys = set()
        deduped_instances = []
        for inst in instances:
            key = tuple(getattr(inst, f) for f in key_fields)
            if key not in seen_keys:
                seen_keys.add(key)
                deduped_instances.append(inst)

        # Existierende Objekte aus DB
        filters = models.Q()
        for key in seen_keys:
            filters |= models.Q(**dict(zip(key_fields, key)))
        existing_objs = list(model_cls.objects.filter(filters))
        existing_keys = {tuple(getattr(e, f)
                               for f in key_fields): e for e in existing_objs}

        # Neue Objekte bulk_create
        to_create = [
            inst for inst in deduped_instances
            if tuple(getattr(inst, f) for f in key_fields) not in existing_keys
        ]
        if to_create:
            model_cls.objects.bulk_create(to_create, ignore_conflicts=True)

        # Alle relevanten Objekte aus DB laden
        final_objs = list(
            model_cls.objects.filter(
                models.Q(**{f"{key_fields[0]}__in": [k[0] for k in seen_keys]})
            )
        )
        final_key_map = {tuple(getattr(o, f)
                               for f in key_fields): o for o in final_objs}
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
        model_deps = {}
        models_to_sort = set(self.instances_by_model.keys())

        for model_cls in models_to_sort:
            deps = set()
            for f in model_cls._meta.concrete_fields:
                if isinstance(f, models.ForeignKey):
                    # nur FK zu Modellen, die geparst wurden
                    remote_model = f.remote_field.model
                    if remote_model in models_to_sort:
                        deps.add(remote_model)
            model_deps[model_cls] = deps

        sorted_models = []
        visited = set()
        temp_mark = set()

        def visit(m):
            if m in visited:
                return
            if m in temp_mark:
                # Zyklus erkannt, ignoriere – FKs werden beim Speichern sowieso gesetzt
                return
            temp_mark.add(m)
            for dep in model_deps.get(m, set()):
                visit(dep)
            temp_mark.remove(m)
            visited.add(m)
            sorted_models.append(m)

        for m in models_to_sort:
            visit(m)

        return sorted_models

    # ------------------------
    # Redirect FK and M2M _parsed fields
    # ------------------------
    def _apply_parsed_references(self, instances_by_model, final_instances_map):
        """
        Setzt alle ForeignKey- und ManyToMany-Felder auf die final gespeicherten Objekte,
        die zuvor als _parsed referenziert wurden.
        """
        for model_cls, instances in instances_by_model.items():
            for inst in instances:
                for attr_name in dir(inst):
                    if attr_name.startswith("_") and attr_name.endswith("_parsed"):
                        parsed = getattr(inst, attr_name)
                        if parsed is None:
                            continue

                        # Bestimme das zugehörige reale Feld
                        # entfernt führendes _ und _parsed
                        field_name = attr_name[1:-7]
                        # field_object = inst._meta.get_field(field_name)

                        if isinstance(parsed, list):  # M2M
                            final_list = []
                            for ref in parsed:
                                ref_map = final_instances_map.get(
                                    type(ref), {})
                                # Key aus den Unique-Feldern bauen
                                unique_sets = PersistenceHandler._get_unique_fields(
                                    None, type(ref))
                                key_fields = unique_sets[0] if unique_sets else None
                                ref_key = tuple(getattr(ref, f)
                                                for f in key_fields) if key_fields else ()
                                final_obj = ref_map.get(ref_key)
                                if final_obj:
                                    final_list.append(final_obj)
                            # M2M-Feld kann erst nach inst.save() gesetzt werden
                            setattr(inst, attr_name, final_list)
                        else:  # FK
                            ref_map = final_instances_map.get(type(parsed), {})
                            unique_sets = PersistenceHandler._get_unique_fields(
                                None, type(parsed))
                            key_fields = unique_sets[0] if unique_sets else None
                            ref_key = tuple(getattr(parsed, f)
                                            for f in key_fields) if key_fields else ()
                            final_obj = ref_map.get(ref_key)
                            if final_obj:
                                setattr(inst, field_name, final_obj)

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
                model_cls.objects.bulk_create(instances)
            else:  # save
                # FK _parsed vorbereiten, aber noch nicht M2M setzen
                self._apply_parsed_references(
                    {model_cls: instances}, final_instances_map)
                for inst in instances:
                    inst.save()

        # 4️⃣ Jetzt alle M2M-Felder aus _parsed setzen
        for model_cls, instances in self.instances_by_model.items():
            for inst in instances:
                for attr_name in dir(inst):
                    if attr_name.startswith("_") and attr_name.endswith("_parsed"):
                        parsed = getattr(inst, attr_name)
                        if parsed is None:
                            continue
                        field_name = attr_name[1:-7]
                        # field_object = inst._meta.get_field(field_name)
                        if isinstance(parsed, list):  # M2M
                            getattr(inst, field_name).set(parsed)
