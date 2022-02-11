import { DownloadOutlined, UploadOutlined } from '@ant-design/icons';
import { faDrawPolygon, faEdit, faEraser, faTrash, faVectorSquare } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import DigitizeButton from '@terrestris/react-geo/dist/Button/DigitizeButton/DigitizeButton';
import SimpleButton from '@terrestris/react-geo/dist/Button/SimpleButton/SimpleButton';
import ToggleGroup from '@terrestris/react-geo/dist/Button/ToggleGroup/ToggleGroup';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import { notification, Upload } from 'antd';
import { Feature } from 'ol';
import GeoJSON from 'ol/format/GeoJSON';
import GML3 from 'ol/format/GML3';
import OlGeometry from 'ol/geom/Geometry';
import MultiPolygon from 'ol/geom/MultiPolygon';
import Polygon from 'ol/geom/Polygon';
import OlVectorLayer from 'ol/layer/Vector';
import OlMap from 'ol/Map';
import OlSourceVector from 'ol/source/Vector';
import React, { ReactElement } from 'react';
import { screenToWgs84 } from '../../../Utils/MapUtils';
import './AreaDigitizeToolbar.css';

const geoJson = new GeoJSON();
const gml3 = new GML3();

export const AreaDigitizeToolbar = ({
  map
}: {
  map: OlMap
}): ReactElement => {

  const getDrawingLayer = () => {
    const drawingLayer: OlVectorLayer<OlSourceVector<OlGeometry>> = DigitizeUtil.getDigitizeLayer(map);
    return drawingLayer;
  };

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
      const geom = feature.getGeometry();
      if (geom) {
        const poly:any = screenToWgs84 (geom);
        coords.push(poly.getCoordinates());
      }
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
        notification.error({ 
          message: 'Error reading GeoJSON geometry',
          description: String(err)
        });
        return;
      }
    } else if (content.startsWith('<')) {
      try {
        geom = gml3.readGeometry(content);
      } catch (err:any) {
        notification.error({ 
          message: 'Error reading GML 3 geometry',
          description: String(err)
        });
      }
    } else {
      notification.error({ 
        message: 'Unsupported format',
        description: 'File seems neither to be GeoJSON nor GML 3.'
      });
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
      notification.error({ 
        message: 'Unsupported geometry type',
        description: 'File does not contain a MultiPolygon'
      });      
    }
  };

  const tools = (
    <>
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
      </ToggleGroup>
      <SimpleButton
        icon={<FontAwesomeIcon icon={faTrash} />}
        onClick={() => deleteAllDrawings()}
        tooltip='Alle Zeichenobjekte löschen'
        tooltipPlacement='bottom'
      />      
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
    </>
  );

  return (
    <div className='tools-container'>{tools}</div>
  );
};
