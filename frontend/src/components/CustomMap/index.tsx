import { Modal } from 'antd';
import Button from 'antd/lib/button';
import type { Geometry } from 'geojson';
import OlLayerTile from 'ol/layer/Tile';
import OlMap from 'ol/Map';
import OlSourceOsm from 'ol/source/OSM';
import OlView from 'ol/View';
import type { ReactElement } from 'react';
import { useCallback, useEffect, useState } from 'react';


const ModalMap = (geom: Geometry): ReactElement => {
    //const ref = useRef<any>()
    //const isVisible = useOnScreen(ref)
    const [isModalVisible, setIsModalVisible] = useState(false);

    const getMap = useCallback(
        () => {
            const center = [ 788453.4890155146, 6573085.729161344 ];
            const layer = new OlLayerTile({
                source: new OlSourceOsm()
            });
        
            return new OlMap({
                target: 'map',
                view: new OlView({
                center: center,
                zoom: 16,
                
                }),
                layers: [layer]
                
            });
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
        if (isModalVisible){
            const center = [ 788453.4890155146, 6573085.729161344 ];
            const layer = new OlLayerTile({
                source: new OlSourceOsm()
            });
        
            new OlMap({
                target: 'map',
                view: new OlView({
                center: center,
                zoom: 16,
                
                }),
                layers: [layer]
                
            });
        }
    }, [isModalVisible]);


    //return <div ref={ref}><MapComponent {...props} style={{height: '200px', width: '200px', minHeight: '200px', minWidth: '200px'}}/></div>


    
    return (
        <>
            <Button type="primary" onClick={showModal}>
                Open Modal
            </Button>
            <Modal title="Basic Modal" visible={isModalVisible} onOk={handleOk} onCancel={handleCancel} destroyOnClose={true} >
                <div id='map' />              
            </Modal>
        </>
    );

};



export default ModalMap;
