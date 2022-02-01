import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { Button, Drawer } from 'antd';
import React, { ReactElement, useRef, useState } from 'react';
import './RulesDrawer.css';

export const RulesDrawer = (): ReactElement => {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [isVisible, setIsVisible] = useState<boolean>(true);
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
        icon={(
          <FontAwesomeIcon
            icon={['fas', isVisible ? 'angle-double-right' : 'angle-double-left']}
          />
        )}
      />
      <Drawer
        placement='right'
        width={500}
        visible={isVisible}
        closable={false}
        mask={false}
      >
          Rules
      </Drawer>
    </>
  );
};
