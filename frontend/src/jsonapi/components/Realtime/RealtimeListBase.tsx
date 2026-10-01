import { useCallback, useEffect, useState } from "react";
import {
  type ListBaseProps,
  ListContextProvider,
  OptionalResourceContextProvider,
  type RaRecord,
  useDataProvider,
  useIsAuthPending,
  useListController,
} from "react-admin";
import type { CrudEvent } from "../../../providers/dataProvider";

const RealtimeListBase = <RecordType extends RaRecord = RaRecord>({
  children,
  loading = null,
  resource,
  ...props
}: ListBaseProps<RecordType>) => {
  const controller = useListController<RecordType>({ resource, ...props });
  const { data } = controller;
  const [snapshot, setSnapshot] = useState<{
    source: typeof data;
    resource: string;
    records: RecordType[];
  }>();
  const dataProvider = useDataProvider();
  const isAuthPending = useIsAuthPending({
    resource: controller.resource,
    action: "list",
  });

  const handleBusEvent = useCallback(
    (event: CrudEvent) => {
      if (event.type !== "updated" || !data) return;
      const ids = new Set(event.payload.ids.map(String));
      const updates = new Map(
        event.payload.records
          ?.filter((record) => ids.has(String(record.id)))
          .map((record) => [String(record.id), record]),
      );
      setSnapshot((previous) => ({
        source: data,
        resource: controller.resource,
        records: (previous?.source === data &&
        previous.resource === controller.resource
          ? previous.records
          : data
        ).map(
          (record) =>
            // Events on this resource's topics carry records of the controller's type.
            (updates.get(String(record.id)) as RecordType | undefined) ??
            record,
        ),
      }));
    },
    [data, controller.resource],
  );

  useEffect(() => {
    if (isAuthPending && !props.disableAuthentication) return;
    const topics =
      data?.map((record) => `resource/${controller.resource}/${record.id}`) ??
      [];
    topics.forEach((topic) => dataProvider.subscribe(topic, handleBusEvent));
    return () => {
      topics.forEach((topic) =>
        dataProvider.unsubscribe(topic, handleBusEvent),
      );
    };
  }, [
    data,
    controller.resource,
    dataProvider,
    handleBusEvent,
    isAuthPending,
    props.disableAuthentication,
  ]);

  if (isAuthPending && !props.disableAuthentication) return loading;

  const value =
    controller.data === undefined
      ? controller
      : {
          ...controller,
          data:
            snapshot &&
            snapshot.source === data &&
            snapshot.resource === controller.resource
              ? snapshot.records
              : controller.data,
        };
  return (
    <OptionalResourceContextProvider value={resource}>
      <ListContextProvider value={value}>{children}</ListContextProvider>
    </OptionalResourceContextProvider>
  );
};

export default RealtimeListBase;
