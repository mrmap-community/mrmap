import { createElement } from 'react';
import { Create, CreateProps, SimpleForm } from 'react-admin';
import useAllowedWebMapServiceOperationFieldDefinitions from './useAllowedWebMapServiceOperationFieldDefinitions';


const CreateAllowedWebMapServiceOperation = ({
  ...rest
}: CreateProps) => {
  const fieldDefinitions = useAllowedWebMapServiceOperationFieldDefinitions()

    return (
      <Create
        {...rest}
      >
        <SimpleForm>
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
      </Create>
    )
};


export default CreateAllowedWebMapServiceOperation;