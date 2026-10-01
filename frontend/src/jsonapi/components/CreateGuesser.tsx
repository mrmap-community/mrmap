import { type ReactElement } from 'react';
import { Create, type CreateProps, RaRecord, SaveButton, SimpleForm, SimpleFormProps, Toolbar, useResourceDefinition } from 'react-admin';
import { FieldDefinition } from '../utils';
import { ReferenceManyErrorsProvider } from './ReferenceManyErrorsProvider';
import SchemaFormFields from './SchemaFormFields';
import useGuesserSuccess from '../hooks/useGuesserSuccess';


export const CreateToolbar = () => (
  // To support initialize all fields we need to set alwaysEnable to true
  // see https://github.com/marmelab/react-admin/issues/5796
  <Toolbar>
      <SaveButton alwaysEnable />
  </Toolbar>
);

export interface CreateGuesserProps<RecordType extends RaRecord = RaRecord>
    extends Omit<CreateProps<RecordType>, 'children'> {
  defaultValues?: SimpleFormProps['defaultValues']
  toolbar?: ReactElement | false;
  updateFieldDefinitions?: FieldDefinition[];
  referenceInputs?: ReactElement[]
  simpleFormProps?: Partial<SimpleFormProps>
}


const CreateGuesserBase = (
  {
    mutationOptions,
    toolbar,
    defaultValues,
    updateFieldDefinitions,
    referenceInputs,
    simpleFormProps,
    ...rest
  }: CreateGuesserProps
): ReactElement => {

  const { name, options } = useResourceDefinition({ resource: rest.resource })
  const onSuccess = useGuesserSuccess({ resource: name, action: 'created', redirectTo: rest.redirect, undoable: false });

  // be clear that json:api type is always part of mutationOptions so that the dataprovider has all information he needs
  const _mutationOptions = {
    ...mutationOptions,
    meta: { ...mutationOptions?.meta, type: options?.type },
    onSuccess,
  }

  return (
    <Create
      redirect="list" // default is edit... but this is not possible on async created resources
      mutationOptions={_mutationOptions}
      {...rest}
    >
      <SimpleForm
        toolbar={toolbar ?? <CreateToolbar/>}
        defaultValues={defaultValues}
        {...simpleFormProps}
      >
        <SchemaFormFields operationId={`create_${name}`} overrides={updateFieldDefinitions} />
        {referenceInputs}
      </SimpleForm>
    </Create>
  )
}


const CreateGuesser = (
  {...rest}: CreateGuesserProps
) => {

  return (
    <ReferenceManyErrorsProvider>
        <CreateGuesserBase {...rest}/>
    </ReferenceManyErrorsProvider>
  )
}




export default CreateGuesser

