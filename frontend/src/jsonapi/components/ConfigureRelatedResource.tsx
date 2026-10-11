import { Alert } from "@mui/material";
import {
  Loading,
  SaveButton,
  Toolbar,
  useGetList,
  useNotify,
  useShowContext,
  useTranslate,
} from "react-admin";
import { useFieldsForOperation } from "../hooks/useFieldsForOperation";
import useOperation from "../hooks/useOperation";
import CreateGuesser from "./CreateGuesser";
import EditGuesser from "./EditGuesser";
import SchemaAutocompleteInput from "./SchemaAutocompleteInput";

export interface ConfigureRelatedResourceProps {
  relatedResource: string;
}

/** Configure a service's related settings, querying the relationship so record switches stay fresh. */
export default function ConfigureRelatedResource({
  relatedResource,
}: ConfigureRelatedResourceProps) {
  const { resource, record, refetch: refetchService } = useShowContext();
  const translate = useTranslate();
  const notify = useNotify();
  const canCreate = useOperation(`create_${relatedResource}`);
  const canEdit = useOperation(`partial_update_${relatedResource}`);
  const fields = useFieldsForOperation({
    operationId: `create_${relatedResource}`,
  });
  const source = fields.find(
    (field) =>
      !field.props.multiple &&
      field.component === SchemaAutocompleteInput &&
      field.props.reference === resource,
  )?.props.source;
  const { data, isPending, error, refetch } = useGetList(
    relatedResource,
    {
      pagination: { page: 1, perPage: 25 },
      sort: { field: "id", order: "ASC" },
      filter: {},
      meta: { relatedResource: { resource, id: record?.id } },
    },
    { enabled: record?.id != null },
  );
  const onSuccess = () => {
    void refetch();
    void refetchService();
    notify("ra.notification.updated", {
      type: "info",
      messageArgs: { smart_count: 1 },
    });
  };
  if (!record || isPending) return <Loading />;
  if (error)
    return <Alert severity="error">{translate("serviceShow.loadError")}</Alert>;
  const overrides = source
    ? [{ component: SchemaAutocompleteInput, props: { source, hidden: true } }]
    : undefined;
  if (!data?.length) {
    if (!canCreate || !source)
      return <Alert severity="info">{translate("serviceShow.empty")}</Alert>;
    return (
      <CreateGuesser
        key={`${resource}:${record.id}`}
        resource={relatedResource}
        defaultValues={{ [source]: record }}
        updateFieldDefinitions={overrides}
        redirect={false}
        actions={false}
        mutationOptions={{ onSuccess }}
      />
    );
  }
  if (!canEdit)
    return <Alert severity="info">{translate("serviceShow.readOnly")}</Alert>;
  return (
    <>
      {data.map((setting) => (
        <EditGuesser
          key={`${resource}:${record.id}:${setting.id}`}
          resource={relatedResource}
          id={setting.id}
          redirect={false}
          actions={false}
          mutationOptions={{ onSuccess }}
          updateFieldDefinitions={overrides}
          simpleFormProps={{
            toolbar: (
              <Toolbar>
                <SaveButton />
              </Toolbar>
            ),
          }}
        />
      ))}
    </>
  );
}
