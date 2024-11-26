import { Edit, EditProps, SimpleForm } from 'react-admin';
import AllowedWebMapServiceOperationFields from './AllowedWebMapServiceOperationFields';


export interface EditAllowedWebMapServiceOperationProps extends Partial<EditProps> {

}


const EditAllowedWebMapServiceOperation = ({
  
  ...rest
}: EditAllowedWebMapServiceOperationProps) => {
  
    return (
      <Edit
        mutationMode='pessimistic'
        {...rest}
      >
        <SimpleForm
        >
          <AllowedWebMapServiceOperationFields/>
        </SimpleForm>
      </Edit>
    )
};


export default EditAllowedWebMapServiceOperation;