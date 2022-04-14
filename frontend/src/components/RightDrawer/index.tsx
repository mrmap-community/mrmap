import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { Button, Drawer } from 'antd';
import type OlMap from 'ol/Map';
import type { ReactElement } from 'react';
import { useEffect, useRef, useState } from 'react';
import './index.css';

interface RightDrawerProps {
  map?: OlMap;
  children?: JSX.Element;
}

const width = '500px';

export const RightDrawer = ({ map, children }: RightDrawerProps): ReactElement => {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [isVisible, setIsVisible] = useState<boolean>(true);

  // adjust padding of map div
  useEffect(() => {
    if (map) {
      const mapDiv: any = document.querySelector(`#${map.getTarget()}`);
      if (!isVisible) {
        mapDiv.style.paddingRight = '0';
      } else {
        mapDiv.style.paddingRight = width;
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
        className={`rules-drawer-toggle-button ${isVisible ? 'expanded' : 'collapsed'}`}
        onClick={toggleVisible}
        icon={isVisible ? <RightOutlined /> : <LeftOutlined />}
      />
      <Drawer
        placement="right"
        getContainer={false}
        width={500}
        visible={isVisible}
        closable={false}
        mask={false}
        style={{ zIndex: 1, height: '100%', marginTop: '48px' }}
      >
        {children}
      </Drawer>
    </>
  );
};
