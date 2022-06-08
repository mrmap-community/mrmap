import { olMap, wgs84ToScreen } from '@/utils/map';
import { InfoCircleOutlined } from '@ant-design/icons';
import { faMapLocationDot } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { LayerTree } from '@terrestris/react-geo';
import type { ModalProps } from 'antd';
import { Modal, Popover, Tooltip } from 'antd';
import Button from 'antd/lib/button';
import type { Geometry } from 'geojson';
import Feature from 'ol/Feature';
import GeoJSON from 'ol/format/GeoJSON';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import Fill from 'ol/style/Fill';
import Stroke from 'ol/style/Stroke';
import Style from 'ol/style/Style';
import type { ReactElement, ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useIntl } from 'umi';
import { v4 as uuidv4 } from 'uuid';
import AutoResizeMapComponent from '../AutoResizeMapComponent';

export interface ModalMapProps extends ModalProps {
    geom: Geometry
    geomName?: ReactNode
    buttonText?: ReactNode
}

const ModalMap = ({ 
    geom,
    geomName = undefined,
    buttonText = undefined,
    ...passThroughProps
}: ModalMapProps ): ReactElement => {
    const intl = useIntl();
    const uuid = useMemo(() => {
        return uuidv4();
    }, []);
    const map = olMap;

    const _geomName = useMemo(() => {
        return geomName || passThroughProps.title;
    }, [geomName, passThroughProps.title]);

    const [isModalVisible, setIsModalVisible] = useState(false);


    const showModal = () => {
      setIsModalVisible(true);
    };
  
    const handleOk = () => {
      setIsModalVisible(false);
    };
  
    const handleCancel = () => {
      setIsModalVisible(false);
    };

    useEffect(() => {

        const layers = map.getLayers().getArray().filter(layer => layer.get('id') === uuid);

        if (isModalVisible && layers.length === 0){   
            const geoJson = new GeoJSON();
            const geometry = geoJson.readGeometry(geom);
            const feature = new Feature({
                name: _geomName,
                geometry: wgs84ToScreen(geometry),
            });
            feature.setStyle(new Style({ stroke: new Stroke({color: '#FF0000', width: 1}), fill: new Fill({color: [255,27,27,0.2]})}));

            const vectorSource = new VectorSource({
                features: [feature],
            });

            const vectorLayer = new VectorLayer({
                source: vectorSource,
                properties: {
                    name: <Popover content={JSON.stringify(geom)} title="geojson">{_geomName} <InfoCircleOutlined /></Popover>,
                    id: uuid
                },
            });         
            
            map?.addLayer(vectorLayer);
            map?.getView().fit(vectorSource.getExtent(), );
        } else if (!isModalVisible && layers.length > 0) {
            layers.forEach(layer => map.removeLayer(layer));
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isModalVisible]);
    
  
      
    return (
        <>
            <Button  onClick={showModal}>
                {buttonText ? buttonText: <Tooltip title={intl.formatMessage({ id: 'component.modalMap.buttonTooltipTitle' })}><FontAwesomeIcon icon={faMapLocationDot}/></Tooltip>} 
            </Button>
            <Modal 
                visible={isModalVisible} 
                onOk={handleOk} 
                onCancel={handleCancel} 
                destroyOnClose={true} 
                bodyStyle={{height: '50vh', width: '100%'}}
                {...passThroughProps}
            >
                <AutoResizeMapComponent />
                <LayerTree
                        map={map}
                />    
            </Modal>
        </>
    );

};



export default ModalMap;
