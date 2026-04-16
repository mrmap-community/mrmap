import { createElement, type ReactElement, useMemo } from 'react';
import { Edit, type EditProps, RaRecord, SimpleForm, useRecordContext, useResourceDefinition } from 'react-admin';
import { useFieldsForOperation } from '../hooks/useFieldsForOperation';
import { FieldDefinition } from '../utils';


export interface EditGuesserProps<RecordType extends RaRecord = any>
    extends Omit<EditProps<RecordType>, 'children'> {
  toolbar?: ReactElement | false;
  updateFieldDefinitions?: FieldDefinition[];
  referenceInputs?: ReactElement[]
}

const EditFormGuesser = ({
  toolbar,
  updateFieldDefinitions,
  referenceInputs,
  ...props
}: EditGuesserProps): ReactElement => {
  const { name } = useResourceDefinition(props)

  const record = useRecordContext(props)
  
  const fieldDefinitions = useFieldsForOperation(`partial_update_${name}`)
  const fields = useMemo(
    () => 
      fieldDefinitions.filter(fieldDefinition => !fieldDefinition.props.disabled ).map(
        fieldDefinition => {

          const update = updateFieldDefinitions?.find(def => def.props.source === fieldDefinition.props.source)
          return createElement(
            update?.component || fieldDefinition.component, 
            {
              ...fieldDefinition.props, 
              key: `${fieldDefinition.props.source}-${record?.id}`,
              record: record,
              ...update?.props
            }
          )
        })
    ,[fieldDefinitions, record]
  )


  return (
    <SimpleForm
        toolbar={toolbar}
        sanitizeEmptyValues
      >
        {fields}
        {referenceInputs}
      </SimpleForm>
  )

}

const EditGuesser = (
{
  toolbar,
  updateFieldDefinitions,
  referenceInputs,
  ...props
}: EditGuesserProps): ReactElement => {
  const { options } = useResourceDefinition(props)
  
  return (
    <Edit
      queryOptions={{
        refetchOnReconnect: true,
      }}
      mutationOptions={{ meta: { type: options?.type }}}
      mutationMode='pessimistic'
      {...props}
    >
      <EditFormGuesser
        toolbar={toolbar}
        updateFieldDefinitions={updateFieldDefinitions}
        referenceInputs ={referenceInputs}
        {...props}
      />
    </Edit>
  )
}

export default EditGuesser