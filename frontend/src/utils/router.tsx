import type { MenuDataItem } from "@ant-design/pro-layout";

const traverseRoute = (route: MenuDataItem, name: string): MenuDataItem | undefined => {

    if ( route.name === name ){
      return route;
    } else if ( route.routes && route.routes.length > 0 ){
      return route.routes.find(_route => _route.name === name);
    }
      return undefined
  }
  
export const findRouteByName = (routes: MenuDataItem[], name: string): MenuDataItem | undefined => {
return routes.find(route => traverseRoute(route, name));
};