import _ from 'lodash';
import {
  CreateContext,
  CreateMutationFunction,
  CreateParams,
  HttpError,
  RaRecord,
  useCreate,
  useCreateController,
  useDelete,
  useInfiniteGetList,
  useRecordContext,
  useRegisterMutationMiddleware,
  useResourceContext,
  useUpdate
} from 'ra-core';
import { createElement, Fragment, useCallback, useContext, useEffect, useMemo, useRef } from 'react';
import { AddItemButton, ArrayInput, Loading, RemoveItemButton, SimpleFormIterator, useSimpleFormIterator, useSimpleFormIteratorItem } from 'react-admin';
import { FormProvider, useForm, useFormContext, useWatch } from 'react-hook-form';
import { useFieldsForOperation } from '../hooks/useFieldsForOperation';

export const AddButton = () => {
  const { add } = useSimpleFormIterator();

  const onClick = useCallback(()=>{
    add()
  },[add])

  return (
    <AddItemButton
      onClick={onClick}
    />
  )
}

export const RemoveButton = () => {
  const { source } = useSimpleFormIterator();
  const resource = useResourceContext();

  if (resource === undefined) {
    throw new Error(
      `RemoveButton can't be used without ResourceContext`
  );
  }

  const { remove, index,  } = useSimpleFormIteratorItem();
  const { getValues } = useFormContext();

  const [deleteOne, { isPending, isSuccess }] = useDelete();

  const onClick = useCallback(async ()=>{
    const record = getValues()[source][index]

    if (record.id !== undefined) {
      deleteOne(resource, { id: record.id, previousData: record});
    } else {
      remove();
    }
  },[remove, resource, getValues])

  useEffect(()=>{
    if (isSuccess) {
      // delete on serverside is done successfully
      remove()
    }
  }, [isSuccess])

  return (
    <RemoveItemButton 
      // @ts-expect-error TS2322: onClick will be passed to child anyway
      onClick={() => onClick()}  
      disabled={isPending}
    >
      {isPending ? <Loading/>: <Fragment></Fragment>}
    </RemoveItemButton>
  )
}


interface ReferenceManyInputProps {
  reference: string
  source: string
  target: string
}

export const ReferenceManyInput = (
  {
    reference,
    source,
    target,
  }: ReferenceManyInputProps
) => {
  const initialized = useRef(false);
  // sourounding parent form/resource stuff
  const resource = useResourceContext();
  const record = useRecordContext();
  const {record: createdRecord, } = useCreateController()
  const context = useContext(CreateContext);
  const parentForm = useFormContext();
  const currentRecordValues = record?.[source]
  console.log('cR', context)
  const createFieldDefinitions = useFieldsForOperation({operationId: `create_${reference}`})
  const editFieldDefinitions = useFieldsForOperation({operationId: `edit_${reference}`})
  const fieldDefinitions = record?.id === undefined ? createFieldDefinitions : editFieldDefinitions
  
  const includedObjects = useMemo<RaRecord[]>(() => {
      if (currentRecordValues === undefined) return []
      return currentRecordValues.map((value: RaRecord) => {
          // FIXME: check if all needed field values are contained
          if (typeof value === 'object' && value.id && value.stringRepresentation) {
            return value; // already has completed data
          }
        }).filter((value: any) => value !== undefined)
      }
    , [currentRecordValues])
  
  const missingObjects = useMemo(() => {
    if (currentRecordValues === undefined) return []
    return currentRecordValues.filter((value: RaRecord) => value.id && !includedObjects?.find(obj => obj.id === value.id))
  }, [currentRecordValues, includedObjects])

  if (!initialized.current && missingObjects.length > 0){
    console.debug(
      `No included objects found for ${source} in record.
      This may indicate that the related resource is not included in the API response. 
      Please check the API response and ensure that the related resource is included.
      Otherwise, the autocomplete input needs to fetch the data from the API, 
      which may result in additional requests and slower performance.`
    )
  }

  // dataprovider stuff
  const {
    data,
    isFetched
  } = useInfiniteGetList(
      reference,
      {
        pagination: { page: 1, perPage: 20 },
        meta: { relatedResource: { resource: resource, id: record?.id}},
      },
      {
        enabled: missingObjects.length > 0 && !initialized.current,
      }
  );

  // underlying form to controll references
  const formMethods = useForm();
  const {setError, setValue, clearErrors} = formMethods;
  const values = useWatch({control: formMethods.control, name: source});
  const valuesRef = useRef(values)

  const [ create ] = useCreate();
  const [ update ] = useUpdate();

  const onError = useCallback((index: number, error: unknown) => {
    const httpError = error as HttpError 
    httpError?.body?.errors && Object.entries(httpError?.body?.errors).forEach(([key, value]) => {    
      setError(
        `${source}.${index}.${key}`,
        {message: value as string}
      )
    });    
  },[source])

  const memoizedMiddleWare = useCallback(async (
      resource: string| undefined,
      params: CreateParams,
      next: CreateMutationFunction,
      ...rest: any
  ) => {
      // Do something before the mutation

      // Call the next middleware
      const result = await next(resource, params);
      await Promise.all(values?.map((record: RaRecord, index: number) => {
        const options = {
          onError: (error: unknown) => onError(index, error),
          returnPromise: true as const,
        }
        record[target] = {id: result.data.id}

        if (record.id === undefined) {
          return create(
            reference, 
            { 
              data: record 
            }, 
            options
          )
        }

        return update(
          reference,
          {
            id: record.id,
            data: record,
            previousData: valuesRef.current?.find((value: RaRecord) => value.id === record.id),
          },
          options
        )
      }) ?? [])

      // Do something after the mutation
      // Always return the result
      return result;
    }, [create, onError, reference, target, update, values]);
  
  useRegisterMutationMiddleware(memoizedMiddleWare);

  if (
    (fieldDefinitions.length > 0 && !fieldDefinitions.find(def => def.props.source === target))
  ) {
    throw new Error(
        `Wrong configured ReferenceManyInput: ${target} is not a field of ${reference}`
    );
  }

  /** update values ref on changes */
  useEffect(()=> {
    if (!_.isEqual(values, valuesRef.current)){
      clearErrors(source)
      parentForm.clearErrors()
      valuesRef.current = values
    }
  }, [clearErrors, source, values])

  /** update values ref on changes */
  useEffect(()=>{
    if (isFetched && Array.isArray(data?.pages)) {    
      setValue(source, data?.pages?.flatMap(page => page.data))
      initialized.current = true
    }
  }, [data, isFetched])

  


  return (
    
    <FormProvider {...formMethods} >
      <ArrayInput
       source={source}
       resource={reference}
       //isFetching={missingObjects.length === 0 ? false: isFetching}
       //isPending={missingObjects.length === 0 ? false: isPending}
      >
        <SimpleFormIterator
          inline
          disableReordering
          removeButton={<RemoveButton/>}
        >
            {
              createFieldDefinitions.map(
                (fieldDefinition, index) => {
                  const props: any = {
                    key: `${reference}-${fieldDefinition.props.source}`,
                    ...fieldDefinition.props,
                  }
                  
                  if (fieldDefinition.props.source === target) {
                    props.hidden = true
                    props.defaultValue = record?.id
                  }
                  return createElement(
                    fieldDefinition.component, 
                    props
                  )
                }
                  
              )
            }
        </SimpleFormIterator>
      </ArrayInput>
    </FormProvider>
    
  )
};