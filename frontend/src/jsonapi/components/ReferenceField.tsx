import { Chip, } from '@mui/material';
import { RecordRepresentation, SingleFieldList, useRecordContext } from "react-admin";

export interface ReferenceFieldProps {
  source: string
  reference: string
}


const ReferenceField = ({
  source,
  reference
}: ReferenceFieldProps) => {
  const record = useRecordContext()
  if (record?.[source] === undefined) {
    return null
  }
  return (
    <SingleFieldList
      data={record?.[source] && [record?.[source]]}
      resource={reference}
    >
      <Chip
        sx={{ cursor: 'inherit' }}
        size="small"
        label={<RecordRepresentation resource={reference}/>}
        clickable
    />
    </SingleFieldList>
  )

}


export default ReferenceField