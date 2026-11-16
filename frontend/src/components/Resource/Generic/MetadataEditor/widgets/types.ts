import type { ReactElement, ReactNode } from "react";
import type { Validator } from "react-admin";

/**
 * The props a widget overwrite receives: the merged definition props of the
 * field it replaces (`commonProps` in `jsonapi/utils.tsx` — label, helper
 * text, required, disabled, validate) plus the relationship's `reference`.
 * Widgets pass these on to the react-admin input they wrap; the editor row
 * itself adds nothing else.
 */
export interface MetadataWidgetProps {
  source: string;
  reference?: string;
  label?: ReactNode;
  helperText?: ReactNode;
  required?: boolean;
  disabled?: boolean;
  validate?: Validator | Validator[];
  defaultValue?: unknown;
  [key: string]: unknown;
}

/** the create affordance the schema layer hands to-one relationships */
export interface CreateCapableWidgetProps extends MetadataWidgetProps {
  /** a create dialog element, as `commonProps` hands it to one inputs */
  create?: ReactElement;
  createLabel?: string;
}
