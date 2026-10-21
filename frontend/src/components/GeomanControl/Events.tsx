import { useEffect } from "react";
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