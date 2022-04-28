import { CrownOutlined, HeartOutlined, SmileOutlined } from '@ant-design/icons';
import type { MenuDataItem } from '@ant-design/pro-layout';
//@ts-ignore
import React from 'react';
const IconMap = {
  smile: <SmileOutlined />,
  heart: <HeartOutlined />,
  crown: <CrownOutlined />,
};

export const loopMenuItem = (menus: MenuDataItem[]): MenuDataItem[] =>
  menus.map(({ icon, routes, ...item }) => ({
    ...item,
    icon: icon && IconMap[icon as string],
    routes: routes && loopMenuItem(routes),
  }));

const defaultMenus = [
  {
    path: '/user',
    layout: false,
    routes: [
      {
        path: '/user',
        routes: [
          {
            name: 'login',
            path: '/user/login',
            component: './user/Login',
          },
        ],
      },
      {
        component: './404',
      },
    ],
  },
  {
    path: '/welcome',
    name: 'welcome',
    icon: 'smile',
    component: './Welcome',
    wrappers: [
      '@/wrappers/auth',
    ],
  },
  {
    path: '/registry',
    name: 'registry',
    icon: 'database',
    routes: [
      {
        name: 'wms',
        path: '/registry/wms',
        component: './registry/WmsTable',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        path: '/registry/wms/:id/security',
        component: './registry/WmsSecuritySettings',
        hideInMenu: true,
        routes: [{ path: 'rules' }, { path: 'rules/:ruleId/edit' }, { path: 'rules/add' }],
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        name: 'wfs',
        path: '/registry/wfs',
        component: './registry/WfsTable',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        name: 'csw',
        path: '/registry/csw',
        component: './registry/CswTable',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        name: 'datasets',
        path: '/registry/datasets',
        component: './registry/DatasetTable',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        name: 'layers',
        path: '/registry/layers',
        component: './registry/LayerTable',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        name: 'featuretypes',
        path: '/registry/featuretypes',
        component: './registry/FeatureTypeTable',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        name: 'maps',
        path: '/registry/maps',
        component: './registry/MapTable',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        path: '/registry/maps/add',
        component: './registry/MapEditor',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
      {
        path: '/registry/maps/:id/edit',
        component: './registry/MapEditor',
        wrappers: [
          '@/wrappers/auth',
        ],
      },
    ],
  },
  {
    path: '/jobs',
    name: 'jobs',
    icon: 'database',
    component: 'jobs'
  },
  {
    path: '/',
    redirect: '/welcome',
    wrappers: [
      '@/wrappers/auth',
    ],
  },
  {
    component: './404',
  },
];

export default defaultMenus;
