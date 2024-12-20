import { ReactElement } from "react";
import { ListProps, ListView, Loading, RaRecord } from "react-admin";
import RealtimeListBase from "./RealtimeListBase";

const RealtimeList = <RecordType extends RaRecord = any>({
  debounce,
  disableAuthentication,
  disableSyncWithLocation,
  exporter,
  filter = defaultFilter,
  filterDefaultValues,
  loading = defaultLoading,
  perPage = 10,
  queryOptions,
  resource,
  sort,
  storeKey,
  ...rest
}: ListProps<RecordType>): ReactElement => (
  <RealtimeListBase<RecordType>
      debounce={debounce}
      disableAuthentication={disableAuthentication}
      disableSyncWithLocation={disableSyncWithLocation}
      exporter={exporter}
      filter={filter}
      filterDefaultValues={filterDefaultValues}
      loading={loading}
      perPage={perPage}
      queryOptions={queryOptions}
      resource={resource}
      sort={sort}
      storeKey={storeKey}
  >
      <ListView<RecordType> {...rest} />
  </RealtimeListBase>
);

export default RealtimeList

const defaultFilter = {};
const defaultLoading = <Loading />;