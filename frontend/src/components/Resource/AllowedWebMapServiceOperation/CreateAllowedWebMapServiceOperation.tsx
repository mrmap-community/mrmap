import { Create, CreateProps, SimpleForm } from 'react-admin';
import AllowedWebMapServiceOperationFields from './AllowedWebMapServiceOperationFields';


const CreateAllowedWebMapServiceOperation = ({
  ...rest
}: CreateProps) => {
    return (
      <Create
        {...rest}
      >
        <SimpleForm>
          <AllowedWebMapServiceOperationFields/>
        </SimpleForm>
      </Create>
    )
};


export default CreateAllowedWebMapServiceOperation;