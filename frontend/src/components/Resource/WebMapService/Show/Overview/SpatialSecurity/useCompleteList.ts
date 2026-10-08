import { useEffect } from "react";
import { type RaRecord, useInfiniteGetList } from "react-admin";

const useCompleteList = (
  resource: string,
  serviceId?: RaRecord["id"],
  {
    filter = {},
    enabled = true,
  }: { filter?: Record<string, unknown>; enabled?: boolean } = {},
) => {
  const query = useInfiniteGetList(
    resource,
    {
      filter,
      pagination: { page: 1, perPage: 100 },
      sort: {
        field: "id",
        order: "ASC",
      },
      meta:
        serviceId == null
          ? undefined
          : { relatedResource: { resource: "WebMapService", id: serviceId } },
    },
    { enabled },
  );
  useEffect(() => {
    if (enabled && query.hasNextPage && !query.isFetching && !query.error)
      void query.fetchNextPage();
  }, [
    enabled,
    query.hasNextPage,
    query.isFetching,
    query.error,
    query.fetchNextPage,
  ]);
  return {
    ...query,
    records: query.data?.pages.flatMap((page) => page.data) ?? [],
  };
};

export default useCompleteList;
