import { DownOutlined, UpOutlined } from '@ant-design/icons';
import { Button, Drawer } from 'antd';
import OlMap from 'ol/Map';
import { default as React, useEffect, useRef, useState } from 'react';
import './BottomDrawer.css';

interface OwnProps {
  map?: OlMap;
  children?: JSX.Element;
}

type BottomDrawerProps = OwnProps;

export const BottomDrawer: React.FC<BottomDrawerProps> = ({
  map,
  children
}) => {

  const buttonRef = useRef<HTMLButtonElement>(null);
  const [isVisible, setIsVisible] = useState<boolean>(true);

  // adjust padding of map div
  useEffect( () => {
    if (map) {
      const mapDiv: any = document.querySelector(`#${map.getTarget()}`);
      if (!isVisible) {
        mapDiv.style.paddingBottom = '0px';
      } else {
        mapDiv.style.paddingBottom = '500px';
      }
    }
  }, [map, isVisible]);

  const toggleVisible = () => {
    setIsVisible(!isVisible);
    buttonRef.current?.blur();
  };

  return (
    <>
      <Button
        ref={buttonRef}
        className={'bottom-drawer-toggle-button'}
        type='primary'
        style={{
          bottom: isVisible ? '500px' : 0
        }}
        icon={isVisible ? <DownOutlined /> : <UpOutlined />}
        onClick={toggleVisible}
      />
      <Drawer
        placement='bottom'
        visible={isVisible}
        closable={false}
        mask={false}
        height={500}
        style={{ zIndex: 2 }}
      >
        {children}
      </Drawer>
    </>
  );
};
