import {
    CreateButton,
    ListBase,
    SortPayload,
    useResourceDefinition,
    WithListContext
} from 'react-admin';


import { Divider } from '@mui/material';
import { PropsWithChildren } from 'react';
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
  return (
      <ListBase
          resource={resource}
          sort={sort}
          perPage={withList ? 100 : 1}
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
