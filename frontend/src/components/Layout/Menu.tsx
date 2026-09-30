import { useState } from 'react';
import {
  DashboardMenuItem,
  MenuItemLink,
  MenuProps,
  useResourceDefinitions,
  useSidebarState,
} from 'react-admin';

import DisplaySettingsIcon from '@mui/icons-material/DisplaySettings';
import FeedIcon from '@mui/icons-material/Feed';
import PeopleAltIcon from '@mui/icons-material/PeopleAlt';
import PublicIcon from '@mui/icons-material/Public';
import { Box } from '@mui/material';
import MenuList from '@mui/material/MenuList';
import { createElementIfDefined } from '../../utils';
import SubMenu from './SubMenu';

type MenuOption = {
    group: string;
    order?: number;
};

const groupIcons: Record<string, JSX.Element> = {
    WMS: <FeedIcon />,
    WFS: <FeedIcon />,
    CSW: <FeedIcon />,
    Metadata: <FeedIcon />,
    Accounts: <PeopleAltIcon />,
    Admin: <DisplaySettingsIcon />,
};

const CustomMenu = ({ dense = false }: MenuProps) => {
    const [open] = useSidebarState();
    const resourceDefinitions = useResourceDefinitions();
    const menuResources = Object.values(resourceDefinitions).filter(
        resource => resource.options?.menu
    );
    const groups = menuResources.reduce<Record<string, typeof menuResources>>(
        (result, resource) => {
            const menu = resource.options?.menu as MenuOption;
            (result[menu.group] ??= []).push(resource);
            return result;
        },
        {}
    );
    const groupNames = Object.keys(groups);
    const [expanded, setExpanded] = useState<Record<string, boolean>>(
        () => Object.fromEntries(groupNames.map(group => [group, true]))
    );

    return (
        <Box
            sx={{
                width: open ? 200 : 50,
                marginTop: 1,
                marginBottom: '40px',
                transition: theme =>
                    theme.transitions.create('width', {
                        easing: theme.transitions.easing.sharp,
                        duration: theme.transitions.duration.leavingScreen,
                    }),
            }}
        >
            <MenuList>
                <DashboardMenuItem />
                {groupNames.map(group => (
                    <SubMenu
                        key={group}
                        handleToggle={() =>
                            setExpanded(current => ({
                                ...current,
                                [group]: !current[group],
                            }))
                        }
                        isOpen={expanded[group] ?? true}
                        name={group}
                        icon={groupIcons[group] ?? <FeedIcon />}
                        dense={dense}
                    >
                        {groups[group]
                            .sort((first, second) => {
                                const firstMenu = first.options?.menu as MenuOption;
                                const secondMenu = second.options?.menu as MenuOption;
                                return (firstMenu.order ?? 0) - (secondMenu.order ?? 0);
                            })
                            .map(resource => (
                                <MenuItemLink
                                    key={resource.name}
                                    to={`/${resource.name}`}
                                    state={{ _scrollToTop: true }}
                                    primaryText={resource.options?.label ?? resource.name}
                                    leftIcon={createElementIfDefined(resource.icon)}
                                    dense={dense}
                                />
                            ))}
                    </SubMenu>
                ))}
                <MenuItemLink
                    to="/viewer"
                    state={{ _scrollToTop: true }}
                    primaryText="MapViewer"
                    leftIcon={<PublicIcon />}
                    dense={dense}
                />
            </MenuList>
        </Box>
    );
};

export default CustomMenu;
