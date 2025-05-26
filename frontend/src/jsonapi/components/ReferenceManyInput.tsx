import _ from 'lodash';
import {
  HttpError,
  useCreate,
  useDelete,
  useInfiniteGetList,
  useResourceContext,
  useUpdate
} from 'ra-core';
import { createElement, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrayInput, Loading, RaRecord, RemoveItemButton, SimpleFormIterator, useSimpleFormIterator, useSimpleFormIteratorItem } from 'react-admin';
import { FormProvider, useFieldArray, useForm, useFormContext } from 'react-hook-form';
import { useFieldsForOperation } from '../hooks/useFieldsForOperation';


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
      onClick={() => onClick()}
      disabled={isPending}
    >
      {isPending ? <Loading/>: <></>}
    </RemoveItemButton>
  )
}


interface ReferenceManyInputProps {
  reference: string
  target: string
}

export const ReferenceManyInput = (
  {
    reference,
    target,
  }: ReferenceManyInputProps
) => {
  const source = useMemo(()=> `${reference}s`, [reference])
  const resource = useResourceContext();

  const { getValues: getValuesParent, formState: formStateParent } = useFormContext();

  const [targetValue, setTargetValue] = useState({id: getValuesParent('id')});
  const [simpleFormInteratorKey, setSimpleFormInteratorKey] = useState((Math.random() + 1).toString(36).substring(7));

  const {
    data
  } = useInfiniteGetList(
      reference,
      {
        pagination: { page: 1, perPage: 10 },
        meta: { relatedResource: { resource: resource, ...(targetValue.id && targetValue)}},
      }
  );

  const methods = useForm();
  const values: RaRecord[] = methods.watch(source);
  const valuesRef = useRef(values);

  const { append: appendValue } = useFieldArray({
    control: methods.control, // control props comes from useForm (optional: if you are using FormProvider)
    name: source, // unique name for your Field Array
  });

  const { setError, setValue } = methods;

  const [ create ] = useCreate();
  const [ update ] = useUpdate();
  
  const fieldDefinitions = useFieldsForOperation(`create_${reference}`)

  if (fieldDefinitions.length > 0 && !fieldDefinitions.find(def => def.props.source === target)) {
    throw new Error(
        `Wrong configured ReferenceManyInput: ${target} is not a field of ${reference}`
    );
  }

  const onError = useCallback((index: number, error: unknown) => {
    const httpError = error as HttpError 
    Object.entries(httpError?.body?.errors).forEach(([key, value]) => {    
      setError(
        `${source}.${index}.${key}`,
        {message: value as string}
      )
    });    
  },[source])

  useEffect(()=> {
    if (!_.isEqual(values, valuesRef.current)){
      valuesRef.current = values
    }
  },[values])

  useEffect(()=>{
    if (Array.isArray(data?.pages) && data?.pages.length > 0) {
      
      data?.pages.forEach((page, pageIndex) => {
        page.data.forEach((record, index) => {

          const exists = values?.find((existing: RaRecord) => existing.id === record.id) !== undefined
          !exists && appendValue(record)
        })
      })

      setSimpleFormInteratorKey((Math.random() + 1).toString(36).substring(7))

    }
  }, [data])

  useEffect(()=>{
    if (!formStateParent.isSubmitting && formStateParent.isSubmitSuccessful){
      
      setTargetValue({ id: getValuesParent('id') })

      setValue(source, values?.map((element: any) => {
        element[target] = {id: getValuesParent('id')}
        return element;
      }))
      
      methods.clearErrors()

      values?.forEach((resource, index) => { 
        if (resource.id === undefined){
          create(
            reference, 
            { 
              data: resource 
            }, 
            { 
              onError: (error, variables, context) => onError(index, error)
            }
          )
        } else {
          const previousData = valuesRef.current?.find((value: RaRecord) => value.id === resource.id)
          update(
            reference, 
            { 
              id: resource.id, 
              data: resource,
              previousData: previousData
            }, 
            { 
              onError: (error, variables, context) => onError(index, error)
            }
          )
        }
      })
   }
  }, [formStateParent.isSubmitSuccessful, formStateParent.isSubmitting])

  return (
    targetValue.id === undefined ? null:
    <FormProvider {...methods} >
      <ArrayInput
       source={source}
       resource={reference}
       key={simpleFormInteratorKey}
      >
        <SimpleFormIterator
          inline
          disableReordering
          removeButton={<RemoveButton/>}
        >
            {
              fieldDefinitions.map(
                (fieldDefinition, index) => {
                  const props = {
                    key: `${reference}-${fieldDefinition.props.source}`,
                    ...fieldDefinition.props,
                  }
                  
                  if (fieldDefinition.props.source === target) {
                    props.hidden = true
                    props.defaultValue = targetValue
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