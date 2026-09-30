import { createElement, type ReactElement, useCallback, useMemo } from 'react';
import { Create, type CreateProps, RaRecord, SaveButton, SimpleForm, SimpleFormProps, Toolbar, UseCreateMutateParams, useNotify, useRedirect, useResourceDefinition, useTranslate } from 'react-admin';
import { useFieldsForOperation } from '../hooks/useFieldsForOperation';
import { FieldDefinition } from '../utils';
import { ReferenceManyErrorsProvider, useReferenceManyErrors } from './ReferenceManyErrorsProvider';


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
  const translate = useTranslate();
  const notify = useNotify();
  const redirect = useRedirect();
  const { getErrors } = useReferenceManyErrors();

  const { name, options } = useResourceDefinition({ resource: rest.resource })
  const fieldDefinitions = useFieldsForOperation({operationId: `create_${name}`})
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

  const onSuccess = useCallback((
    data: any, 
    variables: Partial<UseCreateMutateParams<any>>, 
    onMutateResult: unknown, 
    context: any
  )=>{
    const referenceManyErrors = getErrors()
    if (referenceManyErrors.length > 0){
      notify(`resources.${rest.resource}.notifications.updated_with_errors`, {
              type: 'warning',
              messageArgs: {
                smart_count: 1,
                _: translate('ra.notification.updated_with_errors', {
                    smart_count: 1,
                }),
              },
              undoable: rest.mutationMode === 'undoable',
      });
      redirect(
        'edit',
        rest.resource,
        data.id,
        undefined,
        {
            referenceManyErrors: referenceManyErrors,
        },
      );
    } else {
      //TODO: created but with subprocessing errors...
      // notify with the correct message
      notify(`resources.${rest.resource}.notifications.created`, {
            type: 'info',
            messageArgs: {
                smart_count: 1,
                _: translate(`ra.notification.created`, {
                    smart_count: 1,
                }),
            },
            undoable: rest.mutationMode === 'undoable',
        });
      redirect(rest.redirect ?? 'list', rest.resource, data.id, data)
    }
    
  },[rest.resource])

  // be clear that json:api type is always part of mutationOptions so that the dataprovider has all information he needs
  const _mutationOptions = useMemo(() => {
    const mut = (mutationOptions != null) ? { ...mutationOptions, meta: { type: options?.type } } : { meta: { type: options?.type } }       
    mut.onSuccess = onSuccess
    
    return mut
  }, [mutationOptions, options])

  return (
    <Create
      redirect="list" // default is edit... but this is not possible on async created resources
      mutationOptions={_mutationOptions}
      {...rest}
    >
      <SimpleForm
        toolbar={toolbar || <CreateToolbar/>}
        defaultValues={defaultValues}
        {...simpleFormProps}
      >
        {fields}
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

