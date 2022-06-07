import { zoomTo } from '@/utils/map';
import { useMap } from '@terrestris/react-geo';
import { Modal } from 'antd';
import Button from 'antd/lib/button';
import type { Geometry } from 'geojson';
import Feature from 'ol/Feature';
import GeoJSON from 'ol/format/GeoJSON';
import VectorLayer from 'ol/layer/Vector';
import VectorSource from 'ol/source/Vector';
import type { ReactElement } from 'react';
import { useEffect, useState } from 'react';
import AutoResizeMapComponent from '../AutoResizeMapComponent';


const ModalMap = (
    { geom }: { geom: Geometry }
): ReactElement => {
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
            <Button type="primary" onClick={showModal}>
                Open Modal
            </Button>
            <Modal 
                title="Basic Modal" 
                visible={isModalVisible} 
                onOk={handleOk} 
                onCancel={handleCancel} 
                destroyOnClose={true} 
                bodyStyle={{height: '50vh', width: '100%'}}
            >
                <AutoResizeMapComponent id={"map"}/>
            </Modal>
        </>
    );

};



export default ModalMap;
