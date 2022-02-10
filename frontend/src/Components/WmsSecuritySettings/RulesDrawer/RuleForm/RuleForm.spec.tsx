/* eslint-disable @typescript-eslint/no-empty-function */
import '@testing-library/jest-dom/extend-expect';
import { RuleForm } from './RuleForm';

jest.mock ('../../../../Repos/JsonApi');

describe('RuleForm', () => {
  it('is defined', () => {
    expect(RuleForm).toBeDefined();
  });

  // TODO fix "Warning: An update to RuleForm inside a test was not wrapped in act(...)."
  // it('can be rendered', () => {
  //   const setSelectedLayerIds = (ids: string[]) => {};
  //   const setIsRuleEditingActive = () => {};
  //   // mock JsonApi minimally, so no HTTP calls are made and the component can
  //   // at least perform the initial render
  //   (operation as any).mockResolvedValue({
  //     data: {
  //       data: []
  //     }
  //   });
  //   const { container } = render(
  //     <RuleForm 
  //       wmsId={''}
  //       selectedLayerIds={[]} 
  //       setSelectedLayerIds={setSelectedLayerIds} 
  //       setIsRuleEditingActive={setIsRuleEditingActive} 
  //     />);
  //   expect(container).toBeVisible();
  // });
});
