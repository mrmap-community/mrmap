import type { FieldDefinition } from "../../../../jsonapi/utils";

import { useNotify, useShowContext } from "react-admin";

import EditGuesser from "../../../../jsonapi/components/EditGuesser";

export default function ServiceMetadataTab({
  updateFieldDefinitions,
}: {
  /**
   * Fields of the metadata form which a screen of a service renders differently
   * than the schema alone would, e.g. a measurement next to the value it decides.
   */
  updateFieldDefinitions?: FieldDefinition[];
} = {}) {
  const { resource, record, refetch } = useShowContext();
  const notify = useNotify();
  if (!record) return null;
  return (
    <EditGuesser
      key={`${resource}:${record.id}`}
      resource={resource}
      id={record.id}
      redirect={false}
      actions={false}
      updateFieldDefinitions={updateFieldDefinitions}
      mutationOptions={{
        onSuccess: () => {
          void refetch();
          notify("ra.notification.updated", {
            type: "info",
            messageArgs: { smart_count: 1 },
          });
        },
      }}
    />
  );
}
