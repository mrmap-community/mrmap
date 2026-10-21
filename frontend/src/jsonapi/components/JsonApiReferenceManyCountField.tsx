import { RaRecord, ReferenceManyCountProps, sanitizeFieldRestProps, useFieldValue } from "react-admin";

import { Typography } from "@mui/material";

const JsonApiReferenceManyCount = <RecordType extends RaRecord = RaRecord>(
  props: ReferenceManyCountProps<RecordType>
) => {
    const data = useFieldValue({ source: props.source || '' });
    const {
      reference: _reference,
      target: _target,
      filter: _filter,
      sort: _sort,
      link: _link,
      resource: _resource,
      source: _source = 'id',
      timeout: _timeout = 1000,
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

    return (
      data
    )
    
};

export default JsonApiReferenceManyCount;