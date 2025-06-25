import {
    CreateButton,
    ListBase,
    SortPayload,
    useResourceDefinition,
    useTranslate,
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
                <><Divider /><CreateButton/></>: null
            }
            
            <ChangeLogList/>
            {/* {
                withList ? 
                    <div>
                    <SimpleList
                        primaryText={record => (`${record.stringRepresentation}`)}
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
                            {translate('ra.action.show_all', {name: name})}
                        </Box>
                    </Button>
                    </div>
                : null} */}
          </CardWithIcon>
      </ListBase>
  );
};

export default ResourceListCard;
