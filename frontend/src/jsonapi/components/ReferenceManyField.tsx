import { useMemo } from "react";
import { RaRecord, ReferenceManyField, ReferenceManyFieldProps, SortPayload, useRecordContext } from "react-admin";
import useOnError from "../hooks/useOnError";
import useOperation from "../hooks/useOperation";
import useResourceSchema from "../hooks/useResourceSchema";
import { PaginatedSingleFieldList } from "./PaginatedSingleFieldList";

const JsonApiReferenceManyField = <
    RecordType extends RaRecord,
    ReferenceRecordType extends RaRecord = RaRecord,
>(
    props: ReferenceManyFieldProps<RecordType, ReferenceRecordType>
) => {
    const { source, reference, target } = props;
    const record = useRecordContext()

    const listOperation = useOperation(`list_${target}`)
    const nestedListOperation = useOperation(`list_related_${reference}_of_${target}`)
    
    const { sortValues: listSortValues } = useResourceSchema(listOperation?.operationId)
    const { sortValues: nestedListSortValues } = useResourceSchema(nestedListOperation?.operationId)
   
    const sort = useMemo<SortPayload>(()=>{
      const sortValues = nestedListSortValues || listSortValues

      // we define a defaul sort here. 
      // Otherwise {field: 'id', order: 'ASC'} is defined from subcomponent.
      // And not any api provides sort by id by default.
      if (sortValues && sortValues.length > 0) {
        return sortValues[0]
      }
      return {field:'', order: 'ASC'}
    },[listSortValues, nestedListSortValues])

    const preferenceKey = useMemo(()=>(`${nestedListOperation?.operationId || listOperation?.operationId}.manyfield.${source}`),[listOperation,nestedListOperation])
    const onError = useOnError(preferenceKey)

    const sparseFieldsParam = useMemo(()=>{
      const _sparseFieldsParam: any = {}
      _sparseFieldsParam[`fields[${reference}]`] = 'id,string_representation'
      return _sparseFieldsParam
    },[reference])

    return (
      <ReferenceManyField 
        {...props} 
        sort={sort}
        source={'id'}
        perPage={5}
        queryOptions={{
          onError,
          meta: {
            jsonApiParams: {
              ...sparseFieldsParam,
            },
            ...(nestedListOperation && {
                relatedResource: {
                resource: target,
                id: record?.id
              }
            }),
            ...(source && {relatedObjects: record?.[source]})
          }
        }}
        empty="empty"
        emptyText="No Values"
      >
        <PaginatedSingleFieldList visibleCount={3} />
      </ReferenceManyField>
    )
    
};

export default JsonApiReferenceManyField;