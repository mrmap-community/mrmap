import { RecordContext } from "react-admin";

import { useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import ServiceDetailsCard, { ServiceProtocol } from "./ServiceDetailsCard";


const SelectedServiceDetailsCard = (
  {protocol}: {protocol: ServiceProtocol;}
) => {

  const { selectedRecord } = useSelectedRecordContext()

  // the aside of a screen of services only selects a service, so the card answers
  // the attention and the outcome of the runs and jobs of the service beside its
  // identity and offers the way to the screen of the service itself
  return (  
    <RecordContext value={selectedRecord}>
      <ServiceDetailsCard protocol={protocol} attention openDetails />
    </RecordContext>

  )
}


export default SelectedServiceDetailsCard;
