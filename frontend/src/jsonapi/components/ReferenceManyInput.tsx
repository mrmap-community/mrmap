import _ from 'lodash';
import {
  CreateMutationFunction,
  CreateParams,
  HttpError,
  RaRecord,
  UpdateMutationFunction,
  UpdateParams,
  useCreate,
  UseCreateOptions,
  useDelete,
  useInfiniteGetList,
  useRecordContext,
  useRedirect,
  useRegisterMutationMiddleware,
  useResourceContext,
  useUpdate,
  UseUpdateOptions
} from 'ra-core';
import { createElement, Fragment, useCallback, useEffect, useMemo, useRef } from 'react';
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
  const parentForm = useFormContext();
  const currentRecordValues = record?.[source]


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

  const redirect = useRedirect();

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
      resource: string | undefined,
      params: CreateParams | UpdateParams,
      next: CreateMutationFunction | UpdateMutationFunction,
  ) => {
      // Do something before the mutation


      // Call the next middleware
      const result = await next(resource, params);

      if (!record?.id){
        console.log('create new instance', params, result)
      }else{
        console.log('update', params, result)
      }

      // create/update all nested records and wait for all to finish
      const promises = (values ?? []).map((rec: RaRecord, index: number) => {
        // ensure target relation points to parent result
        const data = { ...rec, [target]: { id: result.data.id } } as RaRecord;

        // ask react-admin to return a promise for the mutation
        const createOpts: UseCreateOptions = { returnPromise: true as const } as any;
        const updateOpts: UseUpdateOptions = { returnPromise: true as const } as any;

        if (rec.id === undefined) {
          return create(reference, { data }, createOpts as any);
        }

        return update(
          reference,
          {
            id: rec.id,
            data,
            previousData: valuesRef.current?.find((v: RaRecord) => v.id === rec.id),
          },
          updateOpts as any
        );
      });

      const results = await Promise.allSettled(promises);
      // collect field errors from rejected or fulfilled nested mutations
      const nestedErrors: Array<{ name: string; error: { message: string } }> = [];
      results.forEach((r, idx) => {
        if (r.status === 'rejected') {
          const reason: any = r.reason;
          const httpError = reason as HttpError | undefined;
          const body = httpError?.body ?? reason?.body ?? reason?.response?.body ?? reason;
          const candidateErrors = body?.errors ?? body?.error ?? body?.errors?.errors;
          if (candidateErrors && typeof candidateErrors === 'object') {
            Object.entries(candidateErrors).forEach(([key, value]) => {
              nestedErrors.push({ name: `${source}.${idx}.${key}`, error: { message: value as string } });
            });
          } else {
            nestedErrors.push({ name: `${source}.${idx}`, error: { message: (reason && reason.message) || 'Unknown error' } });
          }
        } else if (r.status === 'fulfilled') {
          const value: any = r.value;
          // react-admin may resolve with a payload that still contains validation errors
          const body = value?.body ?? value?.data ?? value;
          const candidateErrors = body?.errors ?? body?.error ?? body?.validationErrors;
          if (candidateErrors && typeof candidateErrors === 'object') {
            Object.entries(candidateErrors).forEach(([key, value]) => {
              nestedErrors.push({ name: `${source}.${idx}.${key}`, error: { message: value as string } });
            });
          }
        }
      });
        

      if (nestedErrors.length > 0) {
        console.log('huhu')
        // set form errors so user sees field-level messages
        //nestedErrors.forEach(e => setError(e.name, e.error as any));

        if (!record?.id){
          // collect created/updated nested resources so the redirected
          // edit view receives the reference-many items as part of the
          // parent resource payload (so fields show up immediately)
          const nestedSavedItems = results.map(r => {
            if (r.status === 'fulfilled') {
              const v: any = r.value;
              return v?.data ?? v?.body ?? v;
            }
            return undefined;
          }).filter((x): x is any => x !== undefined && x !== null);

          /*redirect(
            'edit',
            resource,
            result.data.id,
            undefined,
            {
              ...result.data,
              [source]: nestedSavedItems,
              __nestedErrors: nestedErrors,
            },

          )*/
        }

        // also throw to indicate the parent mutation should be considered failed
        //throw new Error('One or more nested resources failed to save');
      }
      // Do something after the mutation


      // Always return the result
      console.log('result',result)
      const ruu = {
        ...result,
        errors: [...(result.errors ?? []),...nestedErrors]
      };
      console.log(
        'ruu',ruu
      )
      // this console.log is not printed?!
      return ruu
    }, [create,  reference, target, update, values, record]);
  
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