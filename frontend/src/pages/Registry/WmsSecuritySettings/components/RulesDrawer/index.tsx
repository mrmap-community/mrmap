import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import { Button, Drawer } from 'antd';
import type OlMap from 'ol/Map';
import type { ReactElement } from 'react';
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';
import { RuleForm } from './RuleForm/RuleForm';
import './RulesDrawer.css';
import { RulesTable } from './RulesTable/RulesTable';

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
  const path = useLocation().pathname;

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

  let content;
  if (path.endsWith('edit')) {
    content = (
      <RuleForm
        wmsId={wmsId}
        selectedLayerIds={selectedLayerIds}
        setSelectedLayerIds={setSelectedLayerIds}
        setIsRuleEditingActive={setIsRuleEditingActive}
      />
    );
  } else if (path.endsWith('add')) {
    content = (
      <RuleForm
        wmsId={wmsId}
        selectedLayerIds={selectedLayerIds}
        setSelectedLayerIds={setSelectedLayerIds}
        setIsRuleEditingActive={setIsRuleEditingActive}
      />
    );
  } else {
    content = <RulesTable wmsId={wmsId} />;
  }
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
        style={{ position: 'absolute', zIndex: 1, height: '100%' }}
      >
        {content}
      </Drawer>
    </>
  );
};
