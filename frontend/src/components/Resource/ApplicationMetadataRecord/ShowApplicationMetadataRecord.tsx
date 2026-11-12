import RecordShow from "../Generic/RecordShow/RecordShow";

// the application record is harvested as an xml document; its screen shows the
// stored answer beside the parsed fields, which the dataset and service record
// screens do not offer
const ShowApplicationMetadataRecord = () => <RecordShow documents />;

export default ShowApplicationMetadataRecord;
