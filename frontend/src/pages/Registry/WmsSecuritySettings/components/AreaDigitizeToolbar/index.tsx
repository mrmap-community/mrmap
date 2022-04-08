import { screenToWgs84 } from '@/utils/map';
import { DownloadOutlined, UploadOutlined } from '@ant-design/icons';
import {
  faDrawPolygon,
  faEdit,
  faEraser,
  faTrash,
  faVectorSquare,
} from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { DeleteButton, DrawButton, ModifyButton } from '@terrestris/react-geo';
import SimpleButton from '@terrestris/react-geo/dist/Button/SimpleButton/SimpleButton';
import ToggleGroup from '@terrestris/react-geo/dist/Button/ToggleGroup/ToggleGroup';
import { DigitizeUtil } from '@terrestris/react-geo/dist/Util/DigitizeUtil';
import { notification, Upload } from 'antd';
import { Feature } from 'ol';
import GeoJSON from 'ol/format/GeoJSON';
import GML3 from 'ol/format/GML3';
import type OlGeometry from 'ol/geom/Geometry';
import MultiPolygon from 'ol/geom/MultiPolygon';
import type Polygon from 'ol/geom/Polygon';
import type OlMap from 'ol/Map';
import type { ReactElement } from 'react';
import { FormattedMessage, useIntl } from 'umi';
import './index.css';

const geoJson = new GeoJSON();
const gml3 = new GML3();

export const AreaDigitizeToolbar = ({ map }: { map: OlMap }): ReactElement => {
  const intl = useIntl();

  const getDrawingLayer = () => {
    return DigitizeUtil.getDigitizeLayer(map);
  };

  const deleteAllDrawings = () => {
    getDrawingLayer()?.getSource()?.clear();
  };

  const exportArea = () => {
    const layer = getDrawingLayer();
    const coords: any[] = [];
    layer
      ?.getSource()
      ?.getFeatures()
      .forEach((feature) => {
        const geom = feature.getGeometry();
        if (geom) {
          const poly: any = screenToWgs84(geom);
          coords.push(poly.getCoordinates());
        }
      });
    if (coords.length === 0) {
      return;
    }
    const multiPoly = new MultiPolygon(coords);
    const exportedGeoJson: string = geoJson.writeGeometry(multiPoly, {
      decimals: 7,
    });

    function downloadFile(file: any) {
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
    let geom: OlGeometry | null = null;
    if (content.startsWith('{')) {
      try {
        geom = geoJson.readGeometry(content);
      } catch (err: any) {
        notification.error({
          message: intl.formatMessage({
            id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.importErrorGeoJson',
            defaultMessage: 'Error reading GeoJSON geometry',
          }),
          description: String(err),
        });
        return;
      }
    } else if (content.startsWith('<')) {
      try {
        geom = gml3.readGeometry(content);
      } catch (err: any) {
        notification.error({
          message: intl.formatMessage({
            id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.importErrorGml',
            defaultMessage: 'Error reading GML 3 geometry',
          }),
          description: String(err),
        });
      }
    } else {
      notification.error({
        message: intl.formatMessage({
          id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.importErrorUnsupportedFormat',
          defaultMessage: 'Unsupported format',
        }),
        description: intl.formatMessage({
          id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.importErrorNotGeoJsonNorGml3',
          defaultMessage: 'File seems neither to be GeoJSON nor GML 3.',
        }),
      });
      return;
    }
    if (geom instanceof MultiPolygon) {
      const layer = getDrawingLayer();
      geom.getPolygons().forEach((polygon: Polygon) => {
        const feature = new Feature({
          geometry: polygon.clone().transform('EPSG:4326', 'EPSG:900913'),
        });
        layer?.getSource()?.addFeature(feature);
      });
    } else {
      notification.error({
        message: intl.formatMessage({
          id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.importErrorUnsupportedGeometryType',
          defaultMessage: 'Unsupported geometry type',
        }),
        description: intl.formatMessage({
          id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.importErrorNotMultiPolygons',
          defaultMessage: 'File does not contain a MultiPolygon',
        }),
      });
    }
  };

  return (
    <div className="tools-container">
      <>
        <ToggleGroup orientation="horizontal">
          <DrawButton
            name="drawPolygon"
            drawType="Polygon"
            icon={<FontAwesomeIcon icon={faDrawPolygon} />}
            pressedIcon={<FontAwesomeIcon icon={faDrawPolygon} />}
            tooltip={intl.formatMessage({
              id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.drawPolygon',
              defaultMessage: 'Draw polygon',
            })}
            tooltipPlacement="bottom"
            type="default"
            tooltipProps={{}}
            pressed={false}
          />
          <DrawButton
            name="drawRectangle"
            drawType="Rectangle"
            icon={<FontAwesomeIcon icon={faVectorSquare} />}
            pressedIcon={<FontAwesomeIcon icon={faVectorSquare} />}
            tooltip={intl.formatMessage({
              id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.drawRectangle',
              defaultMessage: 'Draw rectangle',
            })}
            tooltipPlacement="bottom"
            type="default"
            tooltipProps={{}}
            pressed={false}
          />
          <ModifyButton
            name="editArea"
            icon={<FontAwesomeIcon icon={faEdit} />}
            pressedIcon={<FontAwesomeIcon icon={faEdit} />}
            tooltip={intl.formatMessage({
              id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.editArea',
              defaultMessage: 'Edit area',
            })}
            tooltipPlacement="bottom"
            type="default"
            tooltipProps={{}}
            pressed={false}
          />
          <DeleteButton
            name="deleteArea"
            icon={<FontAwesomeIcon icon={faEraser} />}
            pressedIcon={<FontAwesomeIcon icon={faEraser} />}
            tooltip={intl.formatMessage({
              id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.deleteArea',
              defaultMessage: 'Delete area',
            })}
            tooltipPlacement="bottom"
            type="default"
            tooltipProps={{}}
            pressed={false}
          />
        </ToggleGroup>
        <SimpleButton
          icon={<FontAwesomeIcon icon={faTrash} />}
          onClick={() => deleteAllDrawings()}
          tooltip={intl.formatMessage({
            id: 'pages.wmsSecuritySettings.areaDigitizeToolbar.deleteAllAreas',
            defaultMessage: 'Delete all areas',
          })}
          tooltipPlacement="bottom"
        />
        <Upload
          accept=".gml,.geojson,.json"
          beforeUpload={async (file: File) => {
            await importArea(file);
            return false;
          }}
          showUploadList={false}
        >
          <SimpleButton icon={<UploadOutlined />}>
            &nbsp;
            <FormattedMessage
              id="pages.wmsSecuritySettings.areaDigitizeToolbar.importAreas"
              defaultMessage="Import GML 3/GeoJSON"
            />
          </SimpleButton>
        </Upload>
        <SimpleButton icon={<DownloadOutlined />} onClick={exportArea}>
          &nbsp;
          <FormattedMessage
            id="pages.wmsSecuritySettings.areaDigitizeToolbar.exportAreas"
            defaultMessage="Export GeoJSON"
          />
        </SimpleButton>
      </>
    </div>
  );
};
