import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { Button, Drawer } from 'antd';
import React, { ReactElement, useRef, useState } from 'react';
import { Route, Routes } from 'react-router-dom';
import { RuleForm } from '../RuleForm/RuleForm';
import './RulesDrawer.css';
import { RulesTable } from './RulesTable/RulesTable';

export interface RulesDrawerProps {
  wmsId: string,
  selectedLayerIds: string[],
  setSelectedLayerIds: (ids: string[]) => void
}

export const RulesDrawer = ({
  wmsId,
  selectedLayerIds,
  setSelectedLayerIds
}: RulesDrawerProps): ReactElement => {

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
        <Routes>           
          <Route
            path='/'
            element={(
              <RulesTable 
                wmsId={wmsId}
                setSelectedLayerIds={setSelectedLayerIds}
              />
            )}
          />
          <Route
            path='rules/add'
            element={(
              <RuleForm 
                wmsId={wmsId}
                selectedLayerIds={selectedLayerIds}
                setSelectedLayerIds={setSelectedLayerIds}
              />
            )}
          />
          <Route
            path='rules/:ruleId/edit'
            element={(
              <RuleForm 
                wmsId={wmsId}
                selectedLayerIds={selectedLayerIds}
                setSelectedLayerIds={setSelectedLayerIds}
              />
            )}
          />          
        </Routes>
      </Drawer>
    </>
  );
};
