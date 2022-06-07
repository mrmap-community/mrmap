import { zoomTo } from '@/utils/map';
import { faMapLocationDot } from '@fortawesome/free-solid-svg-icons';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useMap } from '@terrestris/react-geo';
import type { ModalProps } from 'antd';
import { Modal, Tooltip } from 'antd';
import Button from 'antd/lib/button';
import type { Geometry } from 'geojson';
import Feature from 'ol/Feature';
import GeoJSON from 'ol/format/GeoJSON';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import type { ReactElement, ReactNode } from 'react';
import { useEffect, useState } from 'react';
import AutoResizeMapComponent from '../AutoResizeMapComponent';

export interface ModalMapProps extends ModalProps {
    geom: Geometry
    buttonText?: ReactNode
}

const ModalMap = ({ 
    geom,
    buttonText = undefined,
    ...passThroughProps
}: ModalMapProps ): ReactElement => {
    //const ref = useRef<any>()
    //const isVisible = useOnScreen(ref)
    const [isModalVisible, setIsModalVisible] = useState(false);
    
    const map = useMap();

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
        const geoJson = new GeoJSON();
        const geometry = geoJson.readGeometry(geom);
        const feature = new Feature({
            name: "Thing",
            geometry: geometry
        });

        const vectorSource = new VectorSource({
            features: [feature],
            });

        const vectorLayer = new VectorLayer({
            source: vectorSource,
        });
        if (isModalVisible){            
            map?.addLayer(vectorLayer);
            zoomTo(map, feature);
        } else {
            map?.removeLayer(vectorLayer);

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
                <AutoResizeMapComponent id={"map"}/>
            </Modal>
        </>
    );

};



export default ModalMap;
