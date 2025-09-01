import {
    CreateButton,
    ListBase,
    SortPayload,
    useResourceDefinition,
    WithListContext
} from 'react-admin';


import { Divider } from '@mui/material';
import { PropsWithChildren, useMemo } from 'react';
import CardWithIcon from './CardWithIcon';
import ChangeLogList from './ChangeLogList';

export interface ResourceListCardProps extends PropsWithChildren {
    resource: string
    sort?: SortPayload
    withList?: boolean
}

const ResourceListCard = (
    {
        resource,
        sort,
        withList = true,
        children
    }: ResourceListCardProps
) => {
  const { name, icon, hasCreate } = useResourceDefinition({ resource: resource })
  const meta = useMemo(()=>{
        if (withList) return {}
        const meta: any = {}
        const sparefields: any = {}
        sparefields[`fields[${resource}]`] = 'id'
        meta["jsonApiParams"] = sparefields
        return meta
      },[withList])
console.log(meta)
  return (
      <ListBase
          resource={resource}
          sort={sort}
          perPage={withList ? 100 : 1}
          queryOptions={{meta: meta}}
          disableSyncWithLocation
      >
          <CardWithIcon
              to={`/${name}`}
              icon={icon}
              title={name}
              subtitle={
                  <WithListContext render={({ total }) => <>{total}</>} />
              }
          > 
            
            {children}
            {
                hasCreate ?
                <><Divider /><CreateButton/></>: <></>
            }
            
            <ChangeLogList/>
            
          </CardWithIcon>
      </ListBase>
  );
};

export default ResourceListCard;
