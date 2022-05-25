import type { MenuDataItem } from '@ant-design/pro-layout';
import { useMemo, useState } from 'react';

const flat = (routes: MenuDataItem[]) => {
  let result: MenuDataItem[] = [];
  routes.forEach( (route) => {
      result.push(route);
      if (Array.isArray(route.routes)) {
          result = result.concat(flat(route.routes));
      }
  });
  return result;
}

export default () => {
  const [routes, setRoutes] = useState<MenuDataItem[]>([])
  const flatRoutes = useMemo<MenuDataItem[]>(() => flat(routes), [routes]);

  return {
    routes,
    flatRoutes,
    setRoutes
  }
}