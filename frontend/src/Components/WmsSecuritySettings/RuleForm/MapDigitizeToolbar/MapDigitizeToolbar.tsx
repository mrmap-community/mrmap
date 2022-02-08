import { faDrawPolygon, faEdit, faEraser, faTrash, faVectorSquare } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import DigitizeButton from '@terrestris/react-geo/dist/Button/DigitizeButton/DigitizeButton';
import SimpleButton from '@terrestris/react-geo/dist/Button/SimpleButton/SimpleButton';
import ToggleGroup from '@terrestris/react-geo/dist/Button/ToggleGroup/ToggleGroup';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import OlGeometry from 'ol/geom/Geometry';
import OlVectorLayer from 'ol/layer/Vector';
import OlMap from 'ol/Map';
import OlSourceVector from 'ol/source/Vector';
import React, { useEffect, useState } from 'react';
import { ToolsContainer } from '../../../Shared/ToolsContainer/ToolsContainer';

interface DefaultProps {
  map: OlMap;
  visible: boolean;
  onClose: () => void;
}

type MapToolbarProps = DefaultProps;

export const MapDigitizeToolbar: React.FC<MapToolbarProps> = ({
  map,
  visible,
  onClose
}) => {

  const [toolsActive, setToolsActive] = useState(false);

  useEffect(() => {
    setToolsActive(visible);
  }, [visible]);

  /**
   * Finds and returns the drawing layer based on the layer name
   * @returns drawingLayer: VectorLayer
   */
  const getDrawingLayer = () => {
    const drawingLayer: OlVectorLayer<OlSourceVector<OlGeometry>> = DigitizeUtil.getDigitizeLayer(map);
    return drawingLayer;
  };

  /**
   * Delete all drawing objects
   */
  const deleteAllDrawings = () => {
    const drawingLayer = getDrawingLayer();
    if (drawingLayer) {
      drawingLayer.getSource().clear();
    }
  };

  const tools = (
    <ToggleGroup orientation='horizontal'>
      <DigitizeButton
        name='drawPolygon'
        map={map}
        drawType='Polygon'
        icon={<FontAwesomeIcon icon={faDrawPolygon} />}
        pressedIcon={<FontAwesomeIcon icon={faDrawPolygon} />}
        tooltip='Polygon zeichnen'
        tooltipPlacement='bottom'
      />
      <DigitizeButton
        name='drawRectangle'
        map={map}
        drawType='Rectangle'
        icon={<FontAwesomeIcon icon={faVectorSquare} />}
        pressedIcon={<FontAwesomeIcon icon={faVectorSquare} />}
        tooltip='Rechteck zeichnen'
        tooltipPlacement='bottom'
      />    
      <DigitizeButton
        name='selectAndModify'
        map={map}
        editType='Edit'
        icon={<FontAwesomeIcon icon={faEdit} />}
        pressedIcon={<FontAwesomeIcon icon={faEdit} />}
        tooltip='Zeichenobjekte editieren'
        tooltipPlacement='bottom'
      />
      <DigitizeButton
        name='deleteFeature'
        map={map}
        editType='Delete'
        icon={<FontAwesomeIcon icon={faEraser} />}
        pressedIcon={<FontAwesomeIcon icon={faEraser} />}
        tooltip='Zeichenobjekt löschen'
        tooltipPlacement='bottom'
      />
      <SimpleButton
        icon={<FontAwesomeIcon icon={faTrash} />}
        onClick={() => deleteAllDrawings()}
        tooltip='Alle Zeichenobjekte löschen'
        tooltipPlacement='bottom'
      />
    </ToggleGroup>
  );

  return (
    <>
      <ToolsContainer
        visible={toolsActive}
        title='Zeichnen'
        tools={tools}
        onClick={() => {
          setToolsActive(!toolsActive);
          onClose();
        }}
      />
    </>
  );
};

export default MapDigitizeToolbar;
