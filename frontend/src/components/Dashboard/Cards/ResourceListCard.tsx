import {
    CreateButton,
    ListBase,
    SimpleList,
    SortPayload,
    useResourceDefinition,
    useTranslate,
    WithListContext,
} from 'react-admin';
import { Link } from 'react-router-dom';

import { Avatar, Box, Button } from '@mui/material';

import { PropsWithChildren } from 'react';
import CardWithIcon from './CardWithIcon';

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
  const translate = useTranslate();
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
                <CreateButton/>: null
            }
            {
                withList ? 
                    <div>
                    <SimpleList
                        primaryText="%{stringRepresentation}"
                        leftAvatar={record => (
                            <Avatar
                                src={`${record.avatar}?size=32x32`}
                                alt={`${record.stringRepresentation}`}
                            />
                        )}
                    />
                    <Box flexGrow={1}>&nbsp;</Box>
                    <Button
                        sx={{ borderRadius: 0 }}
                        component={Link}
                        to={`/${name}`}
                        size="small"
                        color="primary"
                    >
                        <Box p={1} sx={{ color: 'primary.main' }}>
                            {translate('pos.dashboard.all_webmapservices')}
                        </Box>
                    </Button>
                    </div>
                : null}
          </CardWithIcon>
      </ListBase>
  );
};

export default ResourceListCard;
