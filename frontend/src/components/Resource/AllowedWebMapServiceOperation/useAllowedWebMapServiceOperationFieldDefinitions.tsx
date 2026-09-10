import useFieldsForResource from '../../../jsonapi/hooks/useFieldsForResource';
import TreeSelectInput from '../../Input/TreeSelectInput';


const useAllowedWebMapServiceOperationFieldDefinitions = () => {
  return useFieldsForResource({overwrites: [{
    props: {source: 'securedLayers', dependingFieldName: "securedService", helperText: 'select the subtree(s) you want to secure'}, component: TreeSelectInput
  }]})
  
} 

export default useAllowedWebMapServiceOperationFieldDefinitions;