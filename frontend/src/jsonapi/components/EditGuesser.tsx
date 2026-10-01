import { type ReactElement, useMemo } from 'react';
import { DeleteButton, Edit, type EditProps, RaRecord, SaveButton, SimpleForm, SimpleFormProps, Toolbar, ToolbarClasses, useRecordContext, useResourceContext, useResourceDefinition } from 'react-admin';
import { useFieldsForOperation } from '../hooks/useFieldsForOperation';
import useResourceSchema from '../hooks/useResourceSchema';
import { FieldDefinition } from '../utils';
import { ReferenceManyErrorsProvider } from './ReferenceManyErrorsProvider';
import SchemaAutocompleteInput from './SchemaAutocompleteInput';
import type { JsonApiQueryParams } from '../types/jsonapi';
import SchemaFormFields from './SchemaFormFields';
import useGuesserSuccess from '../hooks/useGuesserSuccess';


export interface EditGuesserProps<RecordType extends RaRecord = RaRecord>
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
      <SchemaFormFields operationId={`partial_update_${name}`} overrides={updateFieldDefinitions} record={record} />
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
  const resource = useResourceContext({resource: props.resource})
  
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

    const jsonApiParams: JsonApiQueryParams = {
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
  
  const onSuccess = useGuesserSuccess({ resource: name, action: 'update', redirectTo: props.redirect, undoable: props.mutationMode === 'undoable' });

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
      resource={resource}
      {...props}
    >
      <EditFormGuesser
        updateFieldDefinitions={updateFieldDefinitions}
        referenceInputs ={referenceInputs}
        simpleFormProps={{...simpleFormProps}}
        resource={resource}
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
