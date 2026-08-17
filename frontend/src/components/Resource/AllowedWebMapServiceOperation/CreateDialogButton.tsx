import CreateDialogButton from "../../Dialog/CreateDialogButton";
import AllowedWebMapServiceOperationFields from "./AllowedWebMapServiceOperationFields";

const CreateAllowedWebMapServiceOperationDialogButton = () => {
  return(
    <CreateDialogButton
      createDialogProps={{
        fieldComponent: <AllowedWebMapServiceOperationFields/>
      }}
    />
  )
}

export default CreateAllowedWebMapServiceOperationDialogButton;