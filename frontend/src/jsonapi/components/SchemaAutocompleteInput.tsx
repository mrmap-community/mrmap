import { type ReactElement, useCallback, useMemo, useState } from "react";
import {
  AutocompleteArrayInput,
  AutocompleteArrayInputProps,
  AutocompleteInput,
  GetListParams,
  Identifier,
  type RaRecord,
  useGetList,
  useGetMany,
  useRecordContext,
} from "react-admin";
import { useWatch } from "react-hook-form";

import { RelatedResource } from "../../providers/dataProvider";
import useSchemaRecordRepresentation from "../hooks/useSchemaRecordRepresentation";

export interface SchemaAutocompleteInputProps extends AutocompleteArrayInputProps {
  reference: string;
  relatedResource?: RelatedResource;
  /**
   * Omit `source` inside an ArrayInput row: the input then binds to the whole
   * row value (the row record from the record context) instead of watching a
   * form-root field. This is how an editor row per related record reuses the
   * choices workflow below without watching the array at the form root.
   */
  source?: string;
  params?: GetListParams;
  getListParams?: GetListParams;
  initialFilter?: import("react-admin").FilterPayload;
}

/**
 * DataRequest Workflow:
 * 1. check if record has initial data
 * 2. IF there are initial data, look for completed relation data ({id: 1, stringRepresentation: keyword, keyword: dop40} for example) inside the RaRecord which was collected by the json:api `include` query parameter in any component before
 * 3. IF there is no completed data, collect the information from remote api
 * 4. Fetch available choices when the dropdown opens or the input search changes and merge with the initial data (if any)
 * 5. Merge available choices and completed initial data
 */
const SchemaAutocompleteInput = ({
  reference,
  relatedResource,
  source,
  multiple,
  params,
  defaultValue: _defaultValue,
  getListParams,
  initialFilter,
  onOpen,
  onClose,
  ...rest
}: SchemaAutocompleteInputProps): ReactElement => {
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<import("react-admin").FilterPayload>(initialFilter || {});
  const defaultParms = useMemo<GetListParams>(() => {
    const _defaultParms: GetListParams = {
      sort: { field: "", order: "DESC" },
      meta: {
        relatedResource: relatedResource,
        jsonApiParams: {},
      },
    };
    _defaultParms.meta.jsonApiParams[`fields[${reference}]`] =
      "id,string_representation";
    return _defaultParms;
  }, [reference, relatedResource]);

  const optionText = useSchemaRecordRepresentation({ resource: reference });

  const relatedRecord = useRecordContext(rest);
  // without a source the input is bound to the whole ArrayField row value,
  // which the row's record context carries; the empty-name watch subscribes
  // to no field of the form root
  const formValues:
    Identifier | RaRecord | (Identifier | RaRecord | null)[] | null = useWatch({
    name: source ?? "",
  });
  const boundValues = source === undefined ? (relatedRecord ?? null) : formValues;
  const valuesArray = useMemo(
    () =>
      (Array.isArray(boundValues) ? boundValues : [boundValues])
        .filter((value) => value != null)
        .map((value) => (typeof value === "object" ? value : { id: value }))
        .filter((value) => value.id != null && value.id !== ""),
    [boundValues],
  );

  const includedObjects = useMemo(() => {
    return valuesArray
      .map((value: RaRecord) => {
        if (
          typeof value === "object" &&
          value.id &&
          value.stringRepresentation
        ) {
          return value; // already has completed data
        }
      })
      .filter((value): value is RaRecord => value !== undefined);
  }, [valuesArray]);

  const missingObjects = useMemo(() => {
    return valuesArray.filter(
      (value) =>
        value.id && !includedObjects?.find((obj) => obj.id === value.id),
    );
  }, [valuesArray, includedObjects]);

  if (missingObjects && missingObjects.length > 0) {
    console.warn(
      `No included objects found for ${source} in record ${relatedRecord?.id}.
      This may indicate that the related resource is not included in the API response. 
      Please check the API response and ensure that the related resource is included.
      Otherwise, the autocomplete input needs to fetch the data from the API, 
      which may result in additional requests and slower performance.`,
    );
  }

  const {
    data: searchResults,
    isFetching: searchResultIsFetching,
    isLoading: searchResultIsLoading,
  } = useGetList(
    reference,
    {
      filter: filter,
      ...defaultParms,
      ...getListParams,
      ...params,
    },
    {
      enabled: open || !!filter?.search,
    },
  );

  const {
    data: getManyData,
    isFetching: isFetchingGetMany,
    isLoading: isloadingGetMany,
  } = useGetMany(
    reference,
    {
      ids: missingObjects.map((value) => value.id),
      ...defaultParms,
    },
    {
      enabled: missingObjects.length > 0, // only fetch when there are missing objects
    },
  );

  const mergedData = useMemo(() => {
    return valuesArray.map((value: RaRecord) => {
      if (typeof value === "object" && value.id && value.stringRepresentation) {
        return value; // already has completed data
      }

      const matched = [...(getManyData || [])]?.find(
        (item: RaRecord) =>
          item.id === (typeof value === "object" ? value.id : value),
      );

      return matched || { id: typeof value === "object" ? value.id : value }; // fallback to basic object if no match found
    });
  }, [valuesArray, getManyData]);

  const choices = useMemo(
    () =>
      Array.from(
        new Map<string, RaRecord>(
          [...mergedData, ...(searchResults || [])].map((choice: RaRecord) => [
            String(choice.id),
            choice,
          ]),
        ).values(),
      ),
    [mergedData, searchResults],
  );

  const search = useCallback((searchText: string) => {
    setFilter((prev) => ({ ...prev, search: searchText }));
  }, []);

  // FUTURE: check if the resource has create endpoint; if so, we add an create component here
  if (multiple) {
    return (
      <AutocompleteArrayInput
        setFilter={(searchText: string) => search(searchText)}
        source={source}
        choices={choices}
        isLoading={searchResultIsLoading || isloadingGetMany}
        isFetching={searchResultIsFetching || isFetchingGetMany}
        optionText={optionText}
        inputText={optionText}
        translateChoice={false}
        parse={(value: Identifier[]) => {
          return value?.map((identifier) => ({ id: identifier }));
        }} // form input value (string) ---> parse ---> form state value
        format={(value: (RaRecord | null)[] | null) =>
          value?.filter((record) => record != null).map((record) => record.id)
        }
        {...rest}
        onOpen={(event) => {
          setOpen(true);
          onOpen?.(event);
        }}
        onClose={(event, reason) => {
          setOpen(false);
          onClose?.(event, reason);
        }}
      />
    );
  } else {
    return (
      <AutocompleteInput
        setFilter={(searchText: string) => search(searchText)}
        source={source}
        choices={choices}
        isLoading={searchResultIsLoading || isloadingGetMany}
        isFetching={searchResultIsFetching || isFetchingGetMany}
        optionText={optionText}
        inputText={optionText}
        translateChoice={false}
        parse={(value: Identifier | null) => {
          return value == null || value === "" ? null : { id: value };
        }} // form input value (string) ---> parse ---> form state value
        format={(value: RaRecord) => value?.id}
        {...rest}
        onOpen={(event) => {
          setOpen(true);
          onOpen?.(event);
        }}
        onClose={(event, reason) => {
          setOpen(false);
          onClose?.(event, reason);
        }}
      />
    );
  }
};

export default SchemaAutocompleteInput;
