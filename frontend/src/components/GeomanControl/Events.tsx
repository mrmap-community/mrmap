import { useEffect } from "react";
import { useMap } from "react-leaflet";

interface EventProps extends L.Events {
  onCreate?: (event) => void;
  onUpdate?: (event) => void;
  onRemove?: (event) => void;
}


const Events = ({
  onCreate,
  onUpdate,
  onRemove,
}: EventProps) => {
  const map = useMap();

  useEffect(() => {
    if (map) {
       !map.hasEventListeners("pm:create") && map.on("pm:create", (e) => {
        onCreate && onCreate(e)
        
        onUpdate && !e.layer.hasEventListeners("pm:update") && e.layer.on("pm:update", () => {
           onUpdate(e)
        });

        onRemove && !e.layer.hasEventListeners("pm:remove") && e.layer.on("pm:remove", () => {
           onRemove(e)
        });
      });
    }
  }, [map]);

  return null;
};

export default Events;