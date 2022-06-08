import { olMap } from '@/utils/map';
import MapContext from '@terrestris/react-geo/dist/Context/MapContext/MapContext';
import { Redirect, useAccess } from 'umi';

export default (props: any) => {
  const { isAuthenticated } = useAccess();
  if (isAuthenticated) {
    return <MapContext.Provider value={olMap}>{props.children}</MapContext.Provider>;
  } else {
    return <Redirect to="/user/login" />;
  }
};
