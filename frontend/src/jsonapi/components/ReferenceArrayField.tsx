import { Chip, } from '@mui/material';
import { RecordRepresentation, SingleFieldList, useRecordContext } from "react-admin";

export interface ReferenceArrayFieldProps {
  source: string
  reference: string
}


const ReferenceArrayField = ({
  source,
  reference
}: ReferenceArrayFieldProps) => {
  const record = useRecordContext()

  return (
    <SingleFieldList
      data={record?.[source]}
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


export default ReferenceArrayField