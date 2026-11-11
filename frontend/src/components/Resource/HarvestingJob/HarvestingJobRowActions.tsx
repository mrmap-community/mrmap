import { useRecordContext } from "react-admin";

import { StartAgainButton } from "./HarvestingJobActions";
import StopHarvestingJobButton from "./StopHarvestingJobButton";

/**
 * The action of a row of the list of harvesting runs: a run which did not end
 * is stopped, a run which ended is started again.
 *
 * Both halves are the components the show screen of a run already uses, so the
 * row and the show screen ask the same two things of the same run. The row of
 * an ended run has no stop, because there is nothing left to stop.
 */
const HarvestingJobRowActions = () => {
  const record = useRecordContext();
  if (!record) {
    return null;
  }
  return record.doneAt ? <StartAgainButton /> : <StopHarvestingJobButton />;
};

export default HarvestingJobRowActions;
