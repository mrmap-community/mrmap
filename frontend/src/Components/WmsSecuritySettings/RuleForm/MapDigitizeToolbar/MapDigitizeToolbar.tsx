import { DownloadOutlined, UploadOutlined } from '@ant-design/icons';
import { faDrawPolygon, faEdit, faEraser, faTrash, faVectorSquare } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import DigitizeButton from '@terrestris/react-geo/dist/Button/DigitizeButton/DigitizeButton';
import SimpleButton from '@terrestris/react-geo/dist/Button/SimpleButton/SimpleButton';
import ToggleGroup from '@terrestris/react-geo/dist/Button/ToggleGroup/ToggleGroup';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import { Upload } from 'antd';
import { Feature } from 'ol';
import GeoJSON from 'ol/format/GeoJSON';
import GML3 from 'ol/format/GML3';
import OlGeometry from 'ol/geom/Geometry';
import MultiPolygon from 'ol/geom/MultiPolygon';
import Polygon from 'ol/geom/Polygon';
import OlVectorLayer from 'ol/layer/Vector';
import OlMap from 'ol/Map';
import OlSourceVector from 'ol/source/Vector';
import React, { useEffect, useState } from 'react';
import { ToolsContainer } from '../../../Shared/ToolsContainer/ToolsContainer';

const geoJson = new GeoJSON();
const gml3 = new GML3();

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

  const exportArea = () => {
    const layer = getDrawingLayer();
    const coords: any [] = [];
    layer.getSource().getFeatures().forEach ((feature) => {
      const poly:any = feature.getGeometry()?.clone().transform('EPSG:900913', 'EPSG:4326');
      coords.push(poly.getCoordinates());
    });
    if (coords.length ===  0) {
      return;
    }
    const multiPoly = new MultiPolygon(coords);
    const exportedGeoJson:string = geoJson.writeGeometry(multiPoly, {
      decimals: 7
    });      

    function downloadFile(file:any) {
      const link: any = document.createElement('a');
      link.style.display = 'none';
      link.href = URL.createObjectURL(file);
      link.download = file.name;
      document.body.appendChild(link);
      link.click();
      setTimeout(() => {
        URL.revokeObjectURL(link.href);
        link.parentNode.removeChild(link);
      }, 0);
    }

    const myFile = new File([exportedGeoJson], 'export.geojson');
    downloadFile(myFile);
  };

  const importArea = async (file: File) => {
    const content = (await file.text()).trim();
    let geom: OlGeometry|null = null;
    if (content.startsWith('{')) {
      try {
        geom = geoJson.readGeometry(content);
      } catch (err:any) {
        console.log('Error reading GeoJSON geometry:', err);
        return;
      }
    } else if (content.startsWith('<')) {
      try {
        geom = gml3.readGeometry(content);
      } catch (err:any) {
        console.log('Error reading GML geometry:', err);
        return;
      }
    } else {
      // cannot be JSON or GML
      return;
    }      
    if (geom instanceof MultiPolygon) {
      const layer = getDrawingLayer();
      geom.getPolygons().forEach( (polygon:Polygon) => {
        const feature = new Feature ( {
          geometry: polygon.clone().transform('EPSG:4326', 'EPSG:900913')
        });
        layer.getSource().addFeature(feature);
      });
    } else {
      console.log('Geometry is not a MultiPolygon');
    }
  };

  const tools = (
    <div>
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
      <Upload
        accept='.gml,.geojson,.json'
        beforeUpload={async (file:File)  => {
          await importArea(file);
          return false;
        }}
        showUploadList={false}
      >
        <SimpleButton
          icon={<UploadOutlined />}
          tooltip='Upload GML 3 or GeoJSON'
          tooltipPlacement='bottom'
        >
          Import GML 3/GeoJSON
        </SimpleButton>
      </Upload> 
      <SimpleButton
        icon={<DownloadOutlined />}
        onClick={exportArea}
        tooltip='Export als GeoJSON'
        tooltipPlacement='bottom'
      >
          Export GeoJSON
      </SimpleButton>             
    </div>
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
