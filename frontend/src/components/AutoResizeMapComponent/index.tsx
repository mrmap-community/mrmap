import { MapComponent, useMap } from '@terrestris/react-geo';
import 'ol/ol.css';
import type { ReactElement } from 'react';
import { useEffect } from 'react';


const AutoResizeMapComponent = (
    { 
      divId = 'map' 
    }: {divId?: string}
  ): ReactElement => {
    
  const map = useMap();
 
  

  // automatically call map.updateSize() when mapDiv resizes
  useEffect(() => {
    if (map) {
      map.setTarget(divId);
      const mapDiv: any = document.querySelector(`#${divId}`);
      
      const resizeObserver = new ResizeObserver(() => {
        map.updateSize();
      });
      resizeObserver.observe(mapDiv);
      
      return () => {
        resizeObserver.unobserve(mapDiv);
      };
    }
    return () => {};
  }, [map, divId]);

  if (!map) {
    return <></>;
  }
  return (
      <MapComponent 
        id={divId} 
        map={map} 
        style={{height: '100%', width: '100%'}}
      />
  );
};

export default AutoResizeMapComponent;
