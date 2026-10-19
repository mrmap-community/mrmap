import type { ComponentType } from 'react';

import type { SparseFieldsets } from '../../../../jsonapi/types/jsonapi';


/** The number of services a page of a service list shows. */
export const SERVICE_LIST_PER_PAGE = 25;

/** Services are listed by their title, as they are in the service explorer. */
export const SERVICE_LIST_SORT = { field: 'title', order: 'ASC' } as const;


/** The list of a service, as it is configured in components/Resource/Definition.tsx. */
export interface ServiceListOptions {
  perPage: number;
  sort: { field: string, order: 'ASC' | 'DESC' };
  sparseFieldsets?: SparseFieldsets[];
  additionalActions?: ComponentType;
}


export interface ServiceListOptionsProps {
  /** the json:api type of the service, which names the sparse fieldset of the list */
  type: string;
  /** attributes a row action reads, which are no column of the list */
  fields?: string[];
  /** the actions a row of the list offers in addition to show and edit */
  additionalActions?: ComponentType;
}


/**
 * The list configuration which every registered service shares.
 *
 * All three kinds of services are answered by the same schema driven list
 * (jsonapi/components/ListGuesser and jsonapi/components/ListWithDialogs), so a service
 * does not bring its own list component: it configures the shared one here and only names
 * what differs between them - the attributes its row action reads and the action itself.
 *
 * The fields of a service are asked for as a sparse fieldset, because the attributes which
 * are not a column of the list are not asked for by the datagrid: the secured capabilities
 * of a web map service and the running harvesting job of a catalogue service are only read
 * by their row action. A service without such an attribute asks for nothing extra, which is
 * what the list does without a sparse fieldset.
 *
 * The lists are deliberately not filtered: whether a service needs attention is answered
 * as a column of the list, not as a filter which hides the services without one.
 */
export const serviceListOptions = ({
  type,
  fields = [],
  additionalActions,
}: ServiceListOptionsProps): ServiceListOptions => ({
  perPage: SERVICE_LIST_PER_PAGE,
  sort: { ...SERVICE_LIST_SORT },
  ...(fields.length > 0 && { sparseFieldsets: [{ type, fields }] }),
  ...(additionalActions && { additionalActions }),
});


export default serviceListOptions;
