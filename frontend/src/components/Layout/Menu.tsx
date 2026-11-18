import { useState } from 'react';
import {
  DashboardMenuItem,
  MenuItemLink,
  type ResourceDefinition,
  MenuProps,
  useAuthState,
  useCanAccessResources,
  useResourceDefinitions,
  useSidebarState,
  useTranslate,
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

const groupIcons: Record<string, React.ReactElement> = {
    WMS: <FeedIcon />,
    WFS: <FeedIcon />,
    CSW: <FeedIcon />,
    Metadata: <FeedIcon />,
    Accounts: <PeopleAltIcon />,
    Admin: <DisplaySettingsIcon />,
};

/**
 * The label one menu entry shows for its resource: the key an explicit
 * `options.label` names, else the translated plural of the resource's
 * `resources` block, else the resource name itself. A menu entry never
 * renders a translation key (#1085).
 */
const menuLabel = (resource: ResourceDefinition, translate: (key: string, options?: { _: string }) => string) => {
    const configured = resource.options?.label as string | undefined;
    if (configured !== undefined && configured !== resource.name) {
        return translate(configured);
    }
    return translate(`resources.${resource.name}.plural`, { _: resource.name });
};

interface AuthorizedSubMenuProps {
    group: string;
    resources: ResourceDefinition[];
    isOpen: boolean;
    onToggle: () => void;
    dense: boolean;
}

/**
 * One sidebar group, gated by #836's `canAccess`: hidden while the check
 * runs and, once it answered, only over the resources whose `list` action
 * it granted - a group whose every entry was denied would otherwise be an
 * empty submenu advertising screens this user may not open. At module scope
 * on purpose: a component defined inside `CustomMenu` would remount this
 * subtree - and its access check - on every sidebar toggle.
 */
const AuthorizedSubMenu = ({
    group,
    resources,
    isOpen,
    onToggle,
    dense,
}: AuthorizedSubMenuProps) => {
    const translate = useTranslate();
    const { canAccess, isPending } = useCanAccessResources({
        action: 'list',
        resources: resources.map(resource => resource.name),
    });
    if (isPending) {
        return null;
    }
    const granted = resources.filter(
        resource => canAccess?.[resource.name] === true
    );
    if (granted.length === 0) {
        return null;
    }
    return (
        <SubMenu
            handleToggle={onToggle}
            isOpen={isOpen}
            name={group}
            icon={groupIcons[group] ?? <FeedIcon />}
            dense={dense}
        >
            {granted
                .toSorted((first, second) => {
                    const firstMenu = first.options?.menu as MenuOption;
                    const secondMenu = second.options?.menu as MenuOption;
                    return (firstMenu.order ?? 0) - (secondMenu.order ?? 0);
                })
                .map(resource => (
                    <MenuItemLink
                        key={resource.name}
                        to={`/${resource.name}`}
                        state={{ _scrollToTop: true }}
                        primaryText={menuLabel(resource, translate)}
                        leftIcon={createElementIfDefined(resource.icon)}
                        dense={dense}
                    />
                ))}
        </SubMenu>
    );
};

const CustomMenu = ({ dense = false }: MenuProps) => {
    const translate = useTranslate();
    // #833: the resource groups below answer `canAccess` per entry and so
    // keep the public services of #833 for an anonymous visitor; the three
    // named screens behind a session - dashboard, explorer and viewer - are
    // custom routes guarded by <Authenticated> and are not offered without one
    const { authenticated } = useAuthState();
    const [open] = useSidebarState();
    const resourceDefinitions = useResourceDefinitions();
    const menuResources = Object.values(resourceDefinitions).filter(
        resource => resource.options?.menu
    );
    const groups = menuResources.reduce<Record<string, typeof menuResources>>(
        (result, resource) => {
            const menu = resource.options?.menu as MenuOption;
            const grouped = result[menu.group] ?? [];
            grouped.push(resource);
            result[menu.group] = grouped;
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
                {!!authenticated && <DashboardMenuItem />}
                {!!authenticated && <MenuItemLink to="/service-explorer" primaryText={translate("serviceExplorer.title")} leftIcon={<PublicIcon />} dense={dense} />}
                {groupNames.map(group => (
                    <AuthorizedSubMenu
                        key={group}
                        group={group}
                        resources={groups[group]}
                        isOpen={expanded[group] ?? true}
                        onToggle={() =>
                            setExpanded(current => ({
                                ...current,
                                [group]: !current[group],
                            }))
                        }
                        dense={dense}
                    />
                ))}
                {!!authenticated && <MenuItemLink
                    to="/viewer"
                    state={{ _scrollToTop: true }}
                    primaryText="MapViewer"
                    leftIcon={<PublicIcon />}
                    dense={dense}
                />}
            </MenuList>
        </Box>
    );
};

export default CustomMenu;
