import '@testing-library/jest-dom/extend-expect';
import { render } from '@testing-library/react';
import React from 'react';
import { RuleForm } from './RuleForm';


describe('RuleForm', () => {
  it('is defined', () => {
    expect(RuleForm).toBeDefined();
  });

  it('can be rendered', () => {
    const { container } = render(
      <RuleForm 
        wmsId={''}
        selectedLayerIds={[]} 
        setSelectedLayerIds={function (ids: string[]): void {}} 
        setIsRuleEditingActive={function (isActive: boolean): void {}} 
      />);
    expect(container).toBeVisible();
  });
});
