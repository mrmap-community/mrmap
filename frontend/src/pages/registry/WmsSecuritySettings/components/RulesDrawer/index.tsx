import RightDrawer from '@/components/RightDrawer';
import type OlMap from 'ol/Map';
import type { ReactElement } from 'react';
import { useLocation } from 'react-router';
import RuleForm from '../RuleForm';
import RulesTable from '../RulesTable';

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
  const path = useLocation().pathname;

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
  return <RightDrawer map={map}>{content}</RightDrawer>;
};
