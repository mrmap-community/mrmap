import { Fragment, PropsWithChildren, useMemo } from 'react';
import {
  CreateButton,
  ListBase,
  SortPayload,
  useCanAccess,
  useResourceDefinition,
  WithListContext
} from 'react-admin';

import { Divider } from '@mui/material';

import CardWithIcon from './CardWithIcon';
import ChangeLogList from './ChangeLogList';

export interface ResourceListCardProps extends PropsWithChildren {
    resource: string
    sort?: SortPayload
    withList?: boolean
    compact?: boolean
}

/**
 * The card of one resource of the dashboard.
 *
 * The card which lists records (`withList`) *is* the list of its resource, so it
 * keeps the access gated list controller of react-admin: for a screen, the
 * answer of a denied `list` check is exactly the navigation react-admin performs
 * - to the access denied state.
 *
 * The card which only counts (`withList={false}`) is no screen, it is one number
 * read from the collection of the resource. Mounting the gated controller for it
 * let a single denied check navigate the whole application away, so every caller
 * without an administration role landed on the access denied state instead of the
 * dashboard (#1804). The count card therefore opts out of that controller's check
 * and answers a denied resource the way the other administrator cards of the
 * dashboard answer one: by not rendering at all. `canAccess` is the very check the
 * menu entry and the list of the resource are answered by, so the inventory never
 * advertises a screen its own navigation would refuse.
 */
const ResourceListCard = (
    {
        resource,
        sort,
        withList = true,
        compact = false,
        children
    }: ResourceListCardProps
) => {
  const { name, icon, hasCreate } = useResourceDefinition({ resource: resource })
  const { canAccess, isPending } = useCanAccess({ action: 'list', resource })
  const meta = useMemo(()=>{
        if (withList) return {}
        const meta: { jsonApiParams?: Record<string, string> } = {}
        const sparefields: Record<string, string> = {}
        sparefields[`fields[${resource}]`] = 'id'
        meta["jsonApiParams"] = sparefields
        return meta
      },[withList, resource])

  // the count of a resource the caller may not list is never read and never
  // mounted - an absent card is the answer, not a navigation (#1804)
  if (!withList && (isPending || canAccess === false)) {
    return null
  }

  return (
      <ListBase
          resource={resource}
          filter={['WebMapService', 'WebFeatureService', 'Layer', 'FeatureType'].includes(resource)
            ? { is_update_candidate: false }
            : undefined}
          sort={sort}
          perPage={withList ? 100 : 1}
          queryOptions={{meta: meta}}
          disableAuthentication={!withList}
          disableSyncWithLocation
      >
          <CardWithIcon
              to={`/${name}`}
              icon={icon}
              title={name}
              compact={compact}
              subtitle={
                  <WithListContext render={({ total }) => <Fragment>{total}</Fragment>} />
              }
          >
            {children}
            {!compact && hasCreate ?
                <Fragment><Divider /><CreateButton/></Fragment>: null
            }
            {!compact && <ChangeLogList/>}
          </CardWithIcon>
      </ListBase>
  );
};

export default ResourceListCard;
