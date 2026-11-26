import { useEffect, useMemo, useRef, type MouseEvent, type ReactNode } from 'react';
import { Link } from 'react-admin';

import ErrorIcon from '@mui/icons-material/Error';
import { CircularProgress, Typography, TypographyProps } from '@mui/material';
import {
  Identifier,
  SortPayload,
  useCreatePath,
  useGetList,
  useResourceContext,
  useTimeout,
} from 'ra-core';


/** whether an api error says the caller may not read what was asked for - the
 *  same reading of the http status by which the context of the system status
 *  decides about its indicator (#833). A read which is not allowed is answered
 *  apart from a read which failed, so a count never reads as zero and a
 *  missing permission is not reported as a failure of the api (#1816) */
const isUnauthorized = (error: unknown): boolean => {
  const e = error as { status?: number; response?: { status?: number } };
  const status = e?.status ?? e?.response?.status;
  return status === 401 || status === 403;
};

/** what the read of a `Count` answered, so a screen can answer the state of a
 *  number instead of reading a refused count as a zero or a loading count as a
 *  healthy one - `zero` is the answer of the api that nothing waits, `value`
 *  the answer that something does, and the three others are never healthy */
export type CountState = 'loading' | 'zero' | 'value' | 'forbidden' | 'error';

/**
 * Fetch and render the number of records of a given resource
 *
 * Relies on dataProvider.getList() returning a total property
 *
 * @example // Display the number of records in the current resource (based on ResourceContext)
 * <Count />
 *
 * @example // Display the number of posts
 * <Count resource="posts" />
 *
 * @example // Display the number of published posts
 * <Count resource="posts" filter={{ is_published: true }}/>
 *
 * @example // Display the number of posts, with a custom Typography variant
 * <Count resource="posts" variant="h1" />
 *
 * @see ReferenceManyCount for a similar component which fetches the number of records related to the current one
 */
export const Count = ({
  relatedResource = undefined,
  relatedResourceId = undefined,
  ...props
}: CountProps) => {
    const {
        filter,
        sort,
        link,
        resource: _resourceFromProps,
        timeout = 1000,
        refetchInterval,
        onStateChange,
        ...rest
    } = props;
    const resource = useResourceContext(props);
    if (!resource) {
        throw new Error(
            'The Count component must be used inside a ResourceContext or must be passed a resource prop.'
        );
    }
    if (relatedResource !== undefined && relatedResourceId === undefined){
      throw new Error(
        'You need to define the relatedResourceId.'
      );
    }
    const meta = useMemo(()=>{
      const meta: { jsonApiParams?: Record<string, string>; relatedResource?: { resource: string; id: Identifier } } = {}
      const sparefields: Record<string, string> = {}
      sparefields[`fields[${resource}]`] = 'id'
      meta["jsonApiParams"] = sparefields

      if (relatedResource && relatedResourceId){
        meta['relatedResource'] = {
          resource: relatedResource,
          id: relatedResourceId
        }
      
      }
      return meta
    },[relatedResource, relatedResourceId, resource])

    const oneSecondHasPassed = useTimeout(timeout);
    const createPath = useCreatePath();

    const { total, isPending, error } = useGetList(resource, {
        filter,
        sort,
        pagination: { perPage: 1, page: 1 },
        meta: {
          ...meta

        }
    }, { refetchInterval });

    let body: ReactNode;
    let state: CountState;
    if (isPending) {
        body = oneSecondHasPassed ? <CircularProgress size={14} /> : '';
        state = 'loading';
    } else if (error) {
        // the mark says which of the two answers it is: a queue the caller may
        // not read is not a queue whose api failed
        const unauthorized = isUnauthorized(error);
        body = <ErrorIcon color="error" fontSize="small" titleAccess={unauthorized ? 'unauthorized' : 'error'} />;
        state = unauthorized ? 'forbidden' : 'error';
    } else {
        body = total;
        state = total ? 'value' : 'zero';
    }

    // a screen which answers the state of the read beside the number - the
    // queue of a dashboard must never read a refused count as a zero - learns
    // it from here, because asking the api a second time for the same records
    // is a duplicate request (#1816)
    const report = useRef(onStateChange);
    report.current = onStateChange;
    useEffect(() => {
        report.current?.(state);
    }, [state]);

    return link ? (
        <Link
            to={{
                pathname: createPath({ resource, type: 'list' }),
                search: filter ? `filter=${JSON.stringify(filter)}` : undefined,
            }}
            variant="body2"
            onClick={(e: MouseEvent<HTMLAnchorElement>) => e.stopPropagation()}
            {...rest}
        >
            {body}
        </Link>
    ) : (
        <Typography component="span" variant="body2" {...rest}>
            {body}
        </Typography>
    );
};

export interface CountProps extends TypographyProps {
    refetchInterval?: number | false;
    filter?: import("react-admin").FilterPayload;
    sort?: SortPayload;
    link?: boolean;
    resource?: string;
    relatedResource?: string;
    relatedResourceId?: Identifier;
    timeout?: number;
    /** called with the state of the read, so a screen can answer a refused or
     *  loading count apart from a zero without asking the api twice */
    onStateChange?: (state: CountState, total?: number) => void;
}
