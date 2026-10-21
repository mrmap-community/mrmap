import { RecordContext } from "react-admin";

import { useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import ServiceDetailsCard, { ServiceProtocol } from "./ServiceDetailsCard";


const SelectedServiceDetailsCard = (
  {protocol}: {protocol: ServiceProtocol;}
) => {

  const { selectedRecord } = useSelectedRecordContext()

  return (  
    <RecordContext value={selectedRecord}>
      <ServiceDetailsCard protocol={protocol} />
    </RecordContext>

  )
}


export default SelectedServiceDetailsCard;
