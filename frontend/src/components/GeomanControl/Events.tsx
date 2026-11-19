import { useEffect, useRef } from "react";
import { useMap } from "react-leaflet";

interface EventProps {
  onCreate?: (event: { layer: L.Layer }) => void;
  onUpdate?: (event: { layer: L.Layer }) => void;
  onRemove?: (event: { layer: L.Layer }) => void;
}


const Events = ({
  onCreate,
  onUpdate,
  onRemove,
}: EventProps) => {
  const map = useMap();

  // the pm:create listener is registered once per map, so it must not close
  // over the handlers of one render - it dispatches through this ref instead
  const handlers = useRef({ onCreate, onUpdate, onRemove });
  useEffect(() => {
    handlers.current = { onCreate, onUpdate, onRemove };
  }, [onCreate, onUpdate, onRemove]);

  useEffect(() => {
    if (map) {
       !map.hasEventListeners("pm:create") && map.on("pm:create", (e) => {
        handlers.current.onCreate?.(e)
        
        handlers.current.onUpdate && !e.layer.hasEventListeners("pm:update") && e.layer.on("pm:update", () => {
           handlers.current.onUpdate?.(e)
        });

        handlers.current.onRemove && !e.layer.hasEventListeners("pm:remove") && e.layer.on("pm:remove", () => {
           handlers.current.onRemove?.(e)
        });
      });
    }
  }, [map]);

  return null;
};

export default Events;