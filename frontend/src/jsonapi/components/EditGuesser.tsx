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

const EditGuesser = (
{
  toolbar,
  updateFieldDefinitions,
  referenceInputs,
  ...props
}: EditGuesserProps): ReactElement => {
  const { name, options } = useResourceDefinition(props)

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
    <Edit
      queryOptions={{
        refetchOnReconnect: true,
      }}
      mutationOptions={{ meta: { type: options?.type }}}
      mutationMode='pessimistic'
      {...props}
    >
      <SimpleForm
        toolbar={toolbar}
        sanitizeEmptyValues
      >
        {fields}
        {referenceInputs}
      </SimpleForm>
    </Edit>
  )
}

export default EditGuesser