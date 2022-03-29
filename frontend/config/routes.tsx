import { CrownOutlined, HeartOutlined, SmileOutlined } from '@ant-design/icons';
import type { MenuDataItem } from '@ant-design/pro-layout';
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
  },
  {
    path: '/registry',
    name: 'registry',
    icon: 'database',
    routes: [
      {
        name: 'wms',
        path: '/registry/wms',
        component: './Registry/WmsTable',
      },
      {
        name: 'wfs',
        path: '/registry/wfs',
        component: './Registry/WfsTable',
      },
      {
        name: 'csw',
        path: '/registry/csw',
        component: './Registry/CswTable',
      },
      {
        name: 'layers',
        path: '/registry/layers',
        component: './Registry/LayerTable',
      },
      {
        name: 'featuretypes',
        path: '/registry/featuretypes',
        component: './Registry/FeatureTypeTable',
      },
      {
        name: 'maps',
        path: '/registry/maps',
        component: './Registry/MapTable',
      },
    ],
  },
  {
    path: '/',
    redirect: '/welcome',
  },
  {
    component: './404',
  },
];

export default defaultMenus;
