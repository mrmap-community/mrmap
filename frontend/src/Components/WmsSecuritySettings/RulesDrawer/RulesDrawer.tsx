import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { useMap } from '@terrestris/react-geo';
import { Button, Drawer } from 'antd';
import React, { ReactElement, useRef, useState } from 'react';
import { Route, Routes } from 'react-router-dom';
import { RuleForm } from './RuleForm/RuleForm';
import './RulesDrawer.css';
import { RulesTable } from './RulesTable/RulesTable';

export interface RulesDrawerProps {
  wmsId: string,
  selectedLayerIds: string[],
  setSelectedLayerIds: (ids: string[]) => void,
  setIsRuleEditingActive: (isActive: boolean) => void
}

export const RulesDrawer = ({
  wmsId,
  selectedLayerIds,
  setSelectedLayerIds,
  setIsRuleEditingActive
}: RulesDrawerProps): ReactElement => {

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
        mapDiv.style.paddingRight = '0px';
      } else {
        mapDiv.style.paddingRight = '500px';
      }
    }
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
              <RulesTable wmsId={wmsId}/>
            )}
          />
          <Route
            path='rules/add'
            element={(
              <RuleForm 
                wmsId={wmsId}
                selectedLayerIds={selectedLayerIds}
                setSelectedLayerIds={setSelectedLayerIds}
                setIsRuleEditingActive={setIsRuleEditingActive}
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
                setIsRuleEditingActive={setIsRuleEditingActive}
              />
            )}
          />          
        </Routes>
      </Drawer>
    </>
  );
};
