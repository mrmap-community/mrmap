import { Typography } from "@mui/material";
import { RaRecord, ReferenceManyCountProps, sanitizeFieldRestProps, useFieldValue } from "react-admin";

const JsonApiReferenceManyCount = <RecordType extends RaRecord = RaRecord>(
  props: ReferenceManyCountProps<RecordType>
) => {
    const data = useFieldValue(props.source || '');
    const {
      reference,
      target,
      filter,
      sort,
      link,
      resource,
      source = 'id',
      timeout = 1000,
      ...rest
  } = props;

    if (Array.isArray(data) && data !== null ) {
      
      
      return (
        <Typography
        component="span"
        variant="body2"
        {...sanitizeFieldRestProps(rest)}
    >
        {data.length}
    </Typography>
      )
    }
    console.log('hoho', data)

    return (
      data
    )
    
};

export default JsonApiReferenceManyCount;