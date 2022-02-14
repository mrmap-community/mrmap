import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useMap } from '@terrestris/react-geo';
import { Button, Drawer } from 'antd';
import React, { useRef, useState } from 'react';
import './LeftDrawer.css';

interface OwnProps {
  children?: JSX.Element;
}

type LeftDrawerProps = OwnProps;

export const LeftDrawer: React.FC<LeftDrawerProps> = ({
  children
}) => {

  const map = useMap();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [isVisible, setIsVisible] = useState<boolean>(true);
  const toggleVisible = () => {
    setIsVisible(!isVisible);
    buttonRef.current?.blur();
    // hack map div width
    if (map) {
      const mapDiv: any = document.querySelector(`#${map.getTarget()}`);
      if (isVisible) {
        mapDiv.style.paddingLeft = '0px';
      } else {
        mapDiv.style.paddingLeft = '500px';
      }
    }    
  };

  return (
    <>
      <Button
        ref={buttonRef}
        className={'left-drawer-toggle-button'}
        type='primary'
        style={{
          left: isVisible ? '500px' : 0
        }}
        icon={(
          <FontAwesomeIcon
            icon={['fas', isVisible ? 'angle-double-left' : 'angle-double-right']}
          />
        )}
        onClick={toggleVisible}
      />
      <Drawer
        placement='left'
        getContainer={false}
        visible={isVisible}
        closable={false}
        mask={false}
        width={500}
        style={{ position: 'absolute', zIndex: 1, height: '100vh' }}
      >
        {children}
      </Drawer>
    </>
  );
};

export default LeftDrawer;
