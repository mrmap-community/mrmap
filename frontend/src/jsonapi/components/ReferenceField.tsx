import { useMemo } from "react";
import { ExtractRecordPaths, Link, RaRecord, ReferenceField, ReferenceFieldProps, useFieldValue, useGetRecordRepresentation } from "react-admin";

import { hasIncludedData } from "../utils";

const JsonApiReferenceField = <
    RecordType extends RaRecord = RaRecord,
    ReferenceRecordType extends RaRecord = RaRecord,
>(
    props: ReferenceFieldProps<RecordType, ReferenceRecordType>
) => {
    const data = useFieldValue(props);
    const { source, reference } = props;

    const getRecordRepresentation = useGetRecordRepresentation(reference);
    
    const sparseFieldsParam = useMemo(()=>{
      const _sparseFieldsParam: Record<string, string> = {}
      _sparseFieldsParam[`fields[${reference}]`] = 'id,string_representation'
      return _sparseFieldsParam
    },[])

    if (typeof data === 'object' && !Array.isArray(data) && data !== null && hasIncludedData(data) ) {
      return (
        <Link to={`/${reference}/${data.id}/show`} >
          {getRecordRepresentation(data)}
        </Link>
      )
    }

    return (
      <ReferenceField 
        {...props} 
        source={`${source}.id` as ExtractRecordPaths<RecordType>} 
        queryOptions={{
          meta: {
            jsonApiParams: {
              ...sparseFieldsParam
            }
          }
        }}
      />
    )
    
};

export default JsonApiReferenceField;