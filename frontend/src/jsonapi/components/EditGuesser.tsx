import { createElement, type ReactElement, useCallback, useMemo } from 'react';
import { DeleteButton, Edit, type EditProps, RaRecord, SaveButton, SimpleForm, SimpleFormProps, Toolbar, ToolbarClasses, UseCreateMutateParams, useNotify, useRecordContext, useRedirect, useResourceDefinition, useTranslate } from 'react-admin';
import { useFieldsForOperation } from '../hooks/useFieldsForOperation';
import useResourceSchema from '../hooks/useResourceSchema';
import { FieldDefinition } from '../utils';
import { ReferenceManyErrorsProvider, useReferenceManyErrors } from './ReferenceManyErrorsProvider';
import SchemaAutocompleteInput from './SchemaAutocompleteInput';


export interface EditGuesserProps<RecordType extends RaRecord = any>
    extends Partial<EditProps<RecordType>> {
  updateFieldDefinitions?: FieldDefinition[];
  referenceInputs?: ReactElement[]
  simpleFormProps?: Partial<SimpleFormProps>
}


const EditFormGuesser = ({
  updateFieldDefinitions,
  referenceInputs,
  simpleFormProps,
  ...props
}: EditGuesserProps): ReactElement => {
  const { name, options } = useResourceDefinition(props)

  const record = useRecordContext(props)
  
  const fieldDefinitions = useFieldsForOperation({operationId: `partial_update_${name}`})
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

  const defaultToolbar = useMemo(() => {
    return (
      <Toolbar>
        <div className={ToolbarClasses.defaultToolbar}>
          <SaveButton />
          {/* conditionally include DeleteButton */}
          {options.hasDelete && <DeleteButton resource={name} />}
        </div>
      </Toolbar>
    )
  }, [name, options.hasDelete])

  return (
    <SimpleForm
        toolbar={simpleFormProps?.toolbar ?? defaultToolbar}
        sanitizeEmptyValues
        {...simpleFormProps}
      >
      {fields}
      {referenceInputs}
    </SimpleForm>
  )

}

const EditGuesserBase = (
{
  mutationOptions,
  updateFieldDefinitions,
  referenceInputs,
  simpleFormProps,
  ...props
}: EditGuesserProps): ReactElement => {
  const translate = useTranslate();
  const notify = useNotify();
  const redirect = useRedirect();
  const { getErrors } = useReferenceManyErrors();
  
  const { name, options } = useResourceDefinition(props)
  const {sparseFieldsPerResource, includeAbleResources } = useResourceSchema(`retrieve_${name}`)
  const fieldDefinitions = useFieldsForOperation({operationId: `partial_update_${name}`})
  
  const meta = useMemo(()=>{
    const neededIncludes = fieldDefinitions.filter(
      fieldDefinition => !fieldDefinition.props.disabled && fieldDefinition.component === SchemaAutocompleteInput 
    ).map(fieldDefinition => ({
      source: fieldDefinition.props.source, 
      reference: fieldDefinition.props.reference
    })).filter(include => includeAbleResources?.includes(include.source))

    const jsonApiParams: any = {
      include: neededIncludes.map(include => include.source).join(','),
    }
    const _meta = {
      type: options?.type,
      jsonApiParams: jsonApiParams
    }

    sparseFieldsPerResource && neededIncludes.forEach(include => {
      jsonApiParams[`fields[${include.reference}]`] = 'id,string_representation'
    })
    
    return _meta
  },[ fieldDefinitions, options?.type, sparseFieldsPerResource, includeAbleResources])
  
  const onSuccess = useCallback((
    data: any, 
    variables: Partial<UseCreateMutateParams<any>>, 
    onMutateResult: unknown, 
    context: any
  ) => {

    const referenceManyErrors = getErrors()
    if (referenceManyErrors.length > 0){
      notify(`resources.${props.resource}.notifications.updated_with_errors`, {
              type: 'warning',
              messageArgs: {
                smart_count: 1,
                _: translate('ra.notification.updated_with_errors', {
                    smart_count: 1,
                }),
              },
              undoable: props.mutationMode === 'undoable',
      });
      redirect(
        'edit',
        props.resource,
        data.id,
        undefined,
        {
            referenceManyErrors: referenceManyErrors,
        },
      );
    } else {
      //TODO: updated but with subprocessing errors...
      // notify with the correct message
      notify(`resources.${props.resource}.notifications.update`, {
            type: 'info',
            messageArgs: {
                smart_count: 1,
                _: translate(`ra.notification.update`, {
                    smart_count: 1,
                }),
            },
            undoable: props.mutationMode === 'undoable',
        });
      redirect(props.redirect ?? 'list', props.resource, data.id, data)
    }

  },[props.resource])

  // be clear that json:api type is always part of mutationOptions so that the dataprovider has all information he needs
  const _mutationOptions = useMemo(() => {
    return {
      ...mutationOptions,
      meta: {
        ...meta,
        ...mutationOptions?.meta,
        type: options?.type,
      },
      onSuccess,
    }
  }, [meta, mutationOptions, onSuccess, options?.type])
  
  return (
    <Edit
      queryOptions={{
        refetchOnReconnect: true,
        refetchOnMount:false,
        meta: meta
      }}
      mutationOptions={_mutationOptions}
      mutationMode='pessimistic'
      {...props}
    >
      <EditFormGuesser
        toolbar={toolbar}
        updateFieldDefinitions={updateFieldDefinitions}
        referenceInputs ={referenceInputs}
        simpleFormProps={{...simpleFormProps}}
        {...props}
      />
    </Edit>
  )
}


const EditGuesser = ({...rest}: EditGuesserProps) => {
  return (
    <ReferenceManyErrorsProvider>
      <EditGuesserBase {...rest}/>
    </ReferenceManyErrorsProvider>
  )
}


export default EditGuesser