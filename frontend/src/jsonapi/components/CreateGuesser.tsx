import { createElement, type ReactElement, useMemo } from 'react';
import { Create, type CreateProps, RaRecord, SaveButton, SimpleForm, Toolbar, useResourceDefinition } from 'react-admin';

import { useFieldsForOperation } from '../hooks/useFieldsForOperation';
import { FieldDefinition } from '../utils';


export const CreateToolbar = () => (
  // To support initialize all fields we need to set alwaysEnable to true
  // see https://github.com/marmelab/react-admin/issues/5796
  <Toolbar>
      <SaveButton alwaysEnable />
  </Toolbar>
);

export interface CreateGuesserProps<RecordType extends RaRecord = any>
    extends Omit<CreateProps<RecordType>, 'children'> {
  defaultValues?: any
  toolbar?: ReactElement | false;
  updateFieldDefinitions?: FieldDefinition[];
  referenceInputs?: ReactElement[]
}


const CreateGuesser = (
  {
    mutationOptions,
    toolbar,
    defaultValues,
    updateFieldDefinitions,
    referenceInputs,

    ...rest
  }: CreateGuesserProps
): ReactElement => {
  const { name, options } = useResourceDefinition({ resource: rest.resource })

  const fieldDefinitions = useFieldsForOperation(`create_${name}`)
  const fields = useMemo(
    ()=> 
      fieldDefinitions.filter(fieldDefinition => !fieldDefinition.props.disabled ).map(
        fieldDefinition => {
          const update = updateFieldDefinitions?.find(def => def.props.source === fieldDefinition.props.source)

          return createElement(
            update?.component || fieldDefinition.component, 
            {
              ...fieldDefinition.props, 
              key: fieldDefinition.props.source,
              ...update?.props
            }
          )
        })
    ,[fieldDefinitions]
  )

  // be clear that json:api type is always part of mutationOptions so that the dataprovider has all information he needs
  const _mutationOptions = useMemo(() => {
    return (mutationOptions != null) ? { ...mutationOptions, meta: { type: options?.type } } : { meta: { type: options?.type } }
  }, [mutationOptions])


  return (
    <Create
      redirect="list" // default is edit... but this is not possible on async created resources
      mutationOptions={_mutationOptions}
      {...rest}
    >
      <SimpleForm
        toolbar={toolbar ||<CreateToolbar/>}
        defaultValues={defaultValues}
      >
        {fields}
        {referenceInputs}
      </SimpleForm>
    </Create>
  )
}


export default CreateGuesser