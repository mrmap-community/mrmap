import { olMap, zoomTo } from '@/utils/map';
import { faMapLocationDot } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { LayerTree, useMap } from '@terrestris/react-geo';
import type { ModalProps } from 'antd';
import { Modal, Tooltip } from 'antd';
import Button from 'antd/lib/button';
import type { Geometry } from 'geojson';
import Feature from 'ol/Feature';
import GeoJSON from 'ol/format/GeoJSON';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import type { ReactElement, ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
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

    const [isModalVisible, setIsModalVisible] = useState(false);

    const uuid = useMemo(() => {
        return uuidv4();
    }, []);

    const map = useMap();
    const _geomName = useMemo(() => {
        return geomName || passThroughProps.title;
    }, []);

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
        if (!map){
            return
        }
        console.log(JSON.stringify(geom));
        
        if (isModalVisible){   
            const geoJson = new GeoJSON();
        const geometry = geoJson.readGeometry(geom);
        const feature = new Feature({
            name: _geomName,
            geometry: geometry
        });

        const vectorSource = new VectorSource({
            features: [feature],
            });

        const vectorLayer = new VectorLayer({
            source: vectorSource,
            properties: {
                name: _geomName,
                id: uuid
              },
            
        });         
            map?.addLayer(vectorLayer);
            zoomTo(map, feature);
        } else {
            map.getLayers().getArray()
            .filter(layer => layer.get('id') === uuid)
            .forEach(layer => map.removeLayer(layer));
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [isModalVisible]);
    
  
      
    return (
        <>
            <Button  onClick={showModal}>
                {buttonText ? buttonText: <Tooltip title={'show map'}><FontAwesomeIcon icon={faMapLocationDot}/></Tooltip>} 
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
                        map={map || olMap}
                />
                
            </Modal>
        </>
    );

};



export default ModalMap;
