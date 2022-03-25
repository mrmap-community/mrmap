import { HeartOutlined, SmileOutlined } from '@ant-design/icons';
import type { MenuDataItem } from '@ant-design/pro-layout';

const IconMap = {
  smile: SmileOutlined,
  heart: HeartOutlined
};


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
    name: 'registry',
    icon: 'database',
    routes :[
      {
        name: 'wms',
        icon: 'smile',
        path: '/registry/webmapservices',
        component: './Registry/WebMapServices'
      }
    ]
  },
  {
    path: '/',
    redirect: '/welcome',
  },
  {
    component: './404',
  },
];



export const loopMenuItem = (menus: MenuDataItem[]): MenuDataItem[] =>
  menus.map(({ icon, routes, ...item }) => ({
    ...item,
    icon: icon && IconMap[icon as string],
    routes: routes && loopMenuItem(routes),
  }));


export default defaultMenus;
