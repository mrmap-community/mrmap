import { useMemo } from "react";
import { RaRecord, ReferenceManyField, ReferenceManyFieldProps } from "react-admin";

const JsonApiReferenceManyField = <
    RecordType extends RaRecord,
    ReferenceRecordType extends RaRecord = RaRecord,
>(
    props: ReferenceManyFieldProps<RecordType, ReferenceRecordType>
) => {
    const { source, reference } = props;

    const sparseFieldsParam = useMemo(()=>{
      const _sparseFieldsParam: any = {}
      _sparseFieldsParam[`fields[${reference}]`] = 'id, string_representation'
      return _sparseFieldsParam
    },[])

    return (
      <ReferenceManyField 
        {...props} 
        target={`${source}.id`} 
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

export default JsonApiReferenceManyField;