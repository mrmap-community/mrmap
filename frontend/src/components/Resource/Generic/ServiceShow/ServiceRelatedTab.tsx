import type { ListGuesserProps } from "../../../../jsonapi/components/ListGuesser";
import type { FieldDefinition } from "../../../../jsonapi/utils";

import { type ReactElement, useMemo } from "react";
import {
  BasenameContextProvider,
  CreateButton,
  EditButton,
  ShowButton,
  ResourceContextProvider,
  useNotify,
  useRecordContext,
  useRedirect,
  useResourceContext,
  useResourceDefinition,
  useShowContext,
  useTranslate,
} from "react-admin";

import { Stack, Typography } from "@mui/material";

import ListWithDialogs from "../../../../jsonapi/components/ListWithDialogs";
import SchemaAutocompleteInput from "../../../../jsonapi/components/SchemaAutocompleteInput";
import { useFieldsForOperation } from "../../../../jsonapi/hooks/useFieldsForOperation";

export function ServiceEmptyList() {
  const translate = useTranslate();
  const { hasCreate } = useResourceDefinition();
  return (
    <Stack spacing={1} sx={{ p: 2, alignItems: "flex-start" }}>
      <Typography color="text.secondary">
        {translate("serviceShow.empty")}
      </Typography>
      {hasCreate && <CreateButton />}
    </Stack>
  );
}

export default function ServiceRelatedTab({
  resource,
  formFieldOverrides = [],
  referenceInputs,
  ...listProps
}: {
  resource: string;
  formFieldOverrides?: FieldDefinition[];
  /** extra children of the create and edit dialogs' form, e.g. the
   * schedule preview of a scheduling resource (#1327) */
  referenceInputs?: ReactElement[];
} & Omit<ListGuesserProps, "resource" | "relatedResource">) {
  const parentResource = useResourceContext();
  const record = useRecordContext();
  const { refetch } = useShowContext();
  const notify = useNotify();
  const redirect = useRedirect();
  const { hasEdit, hasShow } = useResourceDefinition({ resource });
  const fields = useFieldsForOperation({ operationId: `create_${resource}` });
  // Derive the reverse relationship from the schema instead of duplicating model fields.
  const parentField = fields.find(
    (field) =>
      !field.props.multiple &&
      field.props.reference === parentResource &&
      field.component === SchemaAutocompleteInput,
  );
  const source = parentField?.props.source;
  const overrides = useMemo(
    () => [
      ...formFieldOverrides,
      ...(source
        ? [
            {
              component: SchemaAutocompleteInput,
              props: { source, hidden: true },
            },
          ]
        : []),
    ],
    [source, formFieldOverrides],
  );
  const onSuccess = () => {
    void refetch();
    notify("ra.notification.updated", {
      type: "info",
      messageArgs: { smart_count: 1 },
    });
    redirect("list", resource);
  };
  if (!record || !parentResource) return null;
  return (
    <ResourceContextProvider value={resource}>
      <ListWithDialogs
        listGuesserProps={{
          resource,
          relatedResource: { resource: parentResource, id: record.id },
          disableSyncWithLocation: true,
          storeKey: `${parentResource}.${record.id}.${resource}`,
          empty: <ServiceEmptyList />,
          aside: undefined,
          rowActions: (
            <>
              {hasShow && (
                <BasenameContextProvider basename="">
                  <ShowButton />
                </BasenameContextProvider>
              )}
              {hasEdit && <EditButton />}
            </>
          ),
          ...listProps,
        }}
        createGuesserProps={{
          resource,
          defaultValues: source ? { [source]: record } : undefined,
          updateFieldDefinitions: overrides,
          referenceInputs,
          mutationOptions: { onSuccess },
        }}
        editGuesserProps={{
          resource,
          updateFieldDefinitions: overrides,
          referenceInputs,
          mutationOptions: { onSuccess },
        }}
      />
    </ResourceContextProvider>
  );
}
