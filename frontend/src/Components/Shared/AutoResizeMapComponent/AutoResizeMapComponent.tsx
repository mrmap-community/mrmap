import { MapComponent, useMap } from '@terrestris/react-geo';
import React, { ReactElement, useEffect } from 'react';

export const AutoResizeMapComponent = (
  { id } :
  { id: string }
): ReactElement => {

  const map = useMap();

  // automatically call map.updateSize() when mapDiv resizes
  useEffect(() => {    
    if (map) {
      map.setTarget(id);
      const mapDiv: any = document.querySelector(`#${id}`);
      const resizeObserver = new ResizeObserver(() => {
        map.updateSize();
      });
      resizeObserver.observe(mapDiv);
      return () => {
        resizeObserver.unobserve(mapDiv);
      };
    }
  }, [map, id]);

  return (
    <MapComponent 
      id={id} 
      map={map} 
    />
  );
};
