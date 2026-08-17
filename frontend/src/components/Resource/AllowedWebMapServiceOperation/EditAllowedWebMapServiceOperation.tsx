import { createElement } from 'react';
import { Edit, EditProps, SimpleForm } from 'react-admin';
import useAllowedWebMapServiceOperationFieldDefinitions from './useAllowedWebMapServiceOperationFieldDefinitions';


export interface EditAllowedWebMapServiceOperationProps extends Partial<EditProps> {

}


const EditAllowedWebMapServiceOperation = ({
  
  ...rest
}: EditAllowedWebMapServiceOperationProps) => {
    const fieldDefinitions = useAllowedWebMapServiceOperationFieldDefinitions()
    return (
      <Edit
        mutationMode='pessimistic'
        {...rest}
      >
        <SimpleForm
          
        >
          {
            fieldDefinitions.map((fieldDefinition, index) =>
                createElement(
                  fieldDefinition.component, 
                  {
                    ...fieldDefinition.props, 
                    key:`create-${rest.resource}-${index}`,
                  }
                )
            )
          }
        </SimpleForm>
      </Edit>
    )
};


export default EditAllowedWebMapServiceOperation;