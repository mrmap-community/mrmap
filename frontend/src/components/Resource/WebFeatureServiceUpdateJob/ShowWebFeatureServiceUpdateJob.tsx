import { type ShowProps } from "react-admin";

import { wfsUpdateConfig } from "../Generic/Update/serviceUpdateConfig";
import { ShowServiceUpdateJob } from "../WebMapServiceUpdateJob/ShowWebMapServiceUpdateJob";

const ShowWebFeatureServiceUpdateJob = (props: ShowProps) => (
  <ShowServiceUpdateJob {...props} config={wfsUpdateConfig} />
);

export default ShowWebFeatureServiceUpdateJob;
