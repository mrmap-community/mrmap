import { useEffect } from "react";
import { type RaRecord, useInfiniteGetList } from "react-admin";

/**
 * Paginates through the complete rule set related to a service; the api answers
 * the related list query for both spatial service types. `jsonApiParams` is
 * passed to the api so callers can `include` the relationships they render.
 */
const useCompleteList = (
  resource: string,
  serviceId?: RaRecord["id"],
  {
    filter = {},
    enabled = true,
    serviceResource = "WebMapService",
    jsonApiParams,
  }: {
    filter?: Record<string, unknown>;
    enabled?: boolean;
    serviceResource?: string;
    jsonApiParams?: Record<string, string>;
  } = {},
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
          : {
              relatedResource: { resource: serviceResource, id: serviceId },
              ...(jsonApiParams && { jsonApiParams }),
            },
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
