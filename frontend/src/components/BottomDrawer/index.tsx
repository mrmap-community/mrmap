import { DownOutlined, UpOutlined } from '@ant-design/icons';
import { Button, Drawer } from 'antd';
import type OlMap from 'ol/Map';
import React, { useEffect, useRef, useState } from 'react';
import './index.css';

interface OwnProps {
  map?: OlMap;
  children?: JSX.Element;
  /* Whether the Drawer dialog is visible or not, can be omitted (automatic) */
  visible?: boolean;
  /* Callback function for when the expand button is clicked */
  onExpand?: (expanded: boolean) => void;
}

type BottomDrawerProps = OwnProps;

const height = '650px';

const BottomDrawer: React.FC<BottomDrawerProps> = ({ map, children, visible, onExpand }) => {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [isVisible, setIsVisible] = useState<boolean>(false);

  useEffect(() => {
    if (visible !== undefined) {
      setIsVisible(visible);
    }
  }, [visible]);

  // adjust padding of map div
  useEffect(() => {
    if (map) {
      const mapDiv: any = document.querySelector(`#${map.getTarget()}`);
      if (!isVisible) {
        mapDiv.style.paddingBottom = '0';
      } else {
        mapDiv.style.paddingBottom = height;
      }
    }
  }, [map, isVisible]);

  const toggleVisible = () => {
    if (onExpand) {
      onExpand(isVisible);
    } else {
      setIsVisible(!isVisible);
    }
    buttonRef.current?.blur();
  };

  return (
    <>
      <Button
        ref={buttonRef}
        className={'bottom-drawer-toggle-button'}
        type="primary"
        style={{
          bottom: isVisible ? height : 0,
        }}
        icon={isVisible ? <DownOutlined /> : <UpOutlined />}
        onClick={toggleVisible}
      />
      <Drawer
        placement="bottom"
        getContainer={false}
        visible={isVisible}
        closable={false}
        mask={false}
        height={height}
        style={{ zIndex: 1001 }}
      >
        {children}
      </Drawer>
    </>
  );
};

export default BottomDrawer;
