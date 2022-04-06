import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { Button, Drawer } from 'antd';
import type OlMap from 'ol/Map';
import type { ReactElement } from 'react';
import { default as React, useEffect, useRef, useState } from 'react';
import './RulesDrawer.css';

export interface RulesDrawerProps {
  wmsId: string;
  selectedLayerIds: string[];
  setSelectedLayerIds: (ids: string[]) => void;
  setIsRuleEditingActive: (isActive: boolean) => void;
  map: OlMap;
}

export const RulesDrawer = ({
  wmsId,
  selectedLayerIds,
  setSelectedLayerIds,
  setIsRuleEditingActive,
  map,
}: RulesDrawerProps): ReactElement => {
  const buttonRef = useRef<HTMLButtonElement>(null);
  const [isVisible, setIsVisible] = useState<boolean>(true);

  // adjust padding of map div
  useEffect(() => {
    if (map) {
      const mapDiv: any = document.querySelector(`#${map.getTarget()}`);
      if (!isVisible) {
        mapDiv.style.paddingRight = '0px';
      } else {
        mapDiv.style.paddingRight = '500px';
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
      <Drawer placement="right" width={500} visible={isVisible} closable={false} mask={false}>
        TODO routing to RuleTable/RuleForm
        <br />- WMS Id:{wmsId}
        <br />- Selected Layer ids: {selectedLayerIds}
        <br />- setSelectedLayerIds: {setSelectedLayerIds}
        <br />- setIsRuleEditingActive: {setIsRuleEditingActive}
        <br />
        {/* <Routes>
          <Route
            path='/'
            element={(
              <RulesTable
                wmsId={wmsId}
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
        </Routes> */}
      </Drawer>
    </>
  );
};
