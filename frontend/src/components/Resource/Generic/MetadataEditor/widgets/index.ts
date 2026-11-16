import type { FieldDefinition } from "../../../../../jsonapi/utils";

import ContactChooser from "./ContactChooser";
import ExtentInput from "./ExtentInput";
import KeywordsInput from "./KeywordsInput";
import TimeExtentsInput from "./TimeExtentsInput";

/**
 * The purpose-built widgets of the metadata editor (#1246), in the shape
 * `useFieldsForOperation`'s `overwrites` takes: each entry replaces the
 * component of the field with the same `props.source` while keeping its
 * schema-derived props (label, reference, required, the create dialog the
 * schema layer hands to-one relationships). Everything else — attributes,
 * the remaining relations — keeps its schema-derived input.
 */
export const METADATA_EDITOR_WIDGETS: FieldDefinition[] = [
  { component: KeywordsInput, props: { source: "keywords" } },
  { component: ContactChooser, props: { source: "metadataContact" } },
  { component: ContactChooser, props: { source: "datasetContact" } },
  { component: ContactChooser, props: { source: "applicationContact" } },
  { component: ExtentInput, props: { source: "boundingGeometry" } },
  { component: TimeExtentsInput, props: { source: "timeExtents" } },
];
