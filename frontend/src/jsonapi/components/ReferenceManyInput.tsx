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
  useLocation,
  useNavigate,
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
import { ReferenceManyError, useReferenceManyErrors } from './ReferenceManyErrorsProvider';

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
  const initializing = useRef(false);
  const initialized = useRef(false);
  // sourounding parent form/resource stuff
  const resource = useResourceContext();
  const record = useRecordContext();
  const parentForm = useFormContext();
  const currentRecordValues = record?.[source]
  const { addErrors } = useReferenceManyErrors();

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
  const navigate = useNavigate();
  const location = useLocation();
  
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

      // Call the next middleware
      const result = await next(resource, params);

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
      const nestedErrors: ReferenceManyError[] = [];
      results.forEach((result, index) => {
        let candidateErrors: Record<string, string> | undefined;

        if (result.status === 'rejected') {
            const reason: any = result.reason;
            const httpError = reason as HttpError | undefined;

            const body =
                httpError?.body ??
                reason?.body ??
                reason?.response?.body ??
                reason;

            candidateErrors =
                body?.errors ??
                body?.error ??
                body?.validationErrors;
        } else {
            const value: any = result.value;

            const body =
                value?.body ??
                value?.data ??
                value;

            candidateErrors =
                body?.errors ??
                body?.error ??
                body?.validationErrors;
        }

        if (
            candidateErrors &&
            typeof candidateErrors === 'object'
        ) {
            nestedErrors.push({
                source,
                index,
                record: values?.[index],
                errors: Object.fromEntries(
                    Object.entries(candidateErrors).map(
                        ([key, value]) => [
                            key,
                            { message: value as string },
                        ]
                    )
                ),
            });
        } else if (result.status === 'rejected') {
            nestedErrors.push({
                source,
                index,
                record: values?.[index],
                errors: {
                    root: {
                        message:
                            (result.reason as any)?.message ??
                            'Unknown error',
                    },
                },
            });
        }
      });
        
      if (nestedErrors.length > 0) {
          nestedErrors.forEach(({ index, errors }) => {
              Object.entries(errors).forEach(([field, error]) => {
                  setError(
                      `${source}.${index}.${field}`,
                      error
                  );
              });
          });

          
          addErrors(nestedErrors);
          
      }

      // Always return the result
      return result
    }, [navigate, location, create,  reference, target, update, values, record]);
  
  useRegisterMutationMiddleware(memoizedMiddleWare);

  if (
    (fieldDefinitions.length > 0 && !fieldDefinitions.find(def => def.props.source === target))
  ) {
    throw new Error(
        `Wrong configured ReferenceManyInput: ${target} is not a field of ${reference}`
    );
  }
  /** update values ref on changes */
  useEffect(() => {
      if (initializing.current) {
          return;
      }

      if (!_.isEqual(values, valuesRef.current)) {
          clearErrors(source);
          parentForm.clearErrors();
          valuesRef.current = values;
      }
  }, [
      clearErrors,
      parentForm,
      source,
      values,
  ]);

  /** update values ref on changes */
  useEffect(() => {
      if (initialized.current) {
          return;
      }

      let serverValues: RaRecord[];

      if (missingObjects.length > 0) {
          if (!isFetched || !Array.isArray(data?.pages)) {
              return;
          }

          serverValues =
              data.pages.flatMap(page => page.data);
      } else {
          serverValues = includedObjects;
      }

      const referenceManyErrors: ReferenceManyError[] =
          location.state?.referenceManyErrors ?? [];

      const sourceErrors = referenceManyErrors
          .filter(error => error.source === source)
          .sort((a, b) => a.index - b.index);

      const restoredValues = [...serverValues];

      sourceErrors.forEach(({ index, record }) => {
          restoredValues.splice(index, 0, record);
      });

      initializing.current = true;

      setValue(source, restoredValues);

      sourceErrors.forEach(({ index, errors }) => {
          Object.entries(errors).forEach(([field, error]) => {
              setError(
                  `${source}.${index}.${field}`,
                  error
              );
          });
      });

      valuesRef.current = restoredValues;
      initialized.current = true;
      initializing.current = false;
  }, [
      data,
      isFetched,
      includedObjects,
      missingObjects.length,
      location.state,
      source,
      setValue,
      setError,
  ]);

  


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