/** The readable form of the durations a run answers about its own work (#1071).

    The api answers measured durations as DRF duration strings and the
    elapsed time and the estimate as seconds; both screens of a run - the
    summary card and the diagnostics tab - show them as the same
    `1h 2m 3s`, which is what the summary card already did before the numbers
    came from the api. `parseDuration` of the jsonapi layer stays the reader
    of the duration string.
*/
import { parseDuration } from "../../../jsonapi/utils";

export const formatSeconds = (seconds: number): string => {
  const total = Math.max(0, Math.floor(seconds));
  return `${Math.floor(total / 3600)}h ${Math.floor(total / 60) % 60}m ${total % 60}s`;
};

export const formatMeasuredDuration = (duration: string): string =>
  formatSeconds(parseDuration(duration));
