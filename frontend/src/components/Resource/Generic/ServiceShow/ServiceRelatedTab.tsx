import { Stack, Typography } from "@mui/material";
import { useMemo } from "react";
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
import ListWithDialogs from "../../../../jsonapi/components/ListWithDialogs";
import type { ListGuesserProps } from "../../../../jsonapi/components/ListGuesser";
import SchemaAutocompleteInput from "../../../../jsonapi/components/SchemaAutocompleteInput";
import type { FieldDefinition } from "../../../../jsonapi/utils";
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
  ...listProps
}: { resource: string; formFieldOverrides?: FieldDefinition[] } & Omit<
  ListGuesserProps,
  "resource" | "relatedResource"
>) {
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
          mutationOptions: { onSuccess },
        }}
        editGuesserProps={{
          resource,
          updateFieldDefinitions: overrides,
          mutationOptions: { onSuccess },
        }}
      />
    </ResourceContextProvider>
  );
}
