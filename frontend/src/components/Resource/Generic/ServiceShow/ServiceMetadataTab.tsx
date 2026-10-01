import { useNotify, useShowContext } from "react-admin";
import EditGuesser from "../../../../jsonapi/components/EditGuesser";

export default function ServiceMetadataTab() {
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
