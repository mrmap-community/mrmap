import type { ReactNode } from "react";
import { type RaRecord, useTranslate } from "react-admin";

import { SelectedRecordContextProvider } from "../../../../jsonapi/components/SelectedRecordContext";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import SimpleCard from "../../../MUI/SimpleCard";
import HistoryList from "../History/HistoryList";

/**
 * The recent changes of one element of a service.
 *
 * The changelog of a service answers what happened on the service; the changes of
 * the layer which is inspected answer what happened to it, which is the question
 * asked next to its details. The compact feed of the changelog asks the selected
 * record context, which is why the element is named to it, and the feed repeats
 * its question when another element is inspected. Without the operation which
 * lists the history of the element, the question can not be answered and the card
 * is absent.
 */
const ElementHistory = ({ resource, record }: { resource: string; record?: RaRecord }): ReactNode => {
  const translate = useTranslate();
  const historyOperation = useOperation(`list_Historical${resource}`);

  if (!historyOperation || record?.id === undefined) {
    return null;
  }

  return (
    <SelectedRecordContextProvider record={record}>
      <SimpleCard
        headerProps={{ sx: { flexShrink: 0 } }}
        contentProps={{
          sx: { p: 0, minHeight: 0, overflowY: "auto", "&:last-child": { pb: 0 } },
        }}
        cardProps={{
          variant: "outlined",
          sx: { width: "100%", maxHeight: 360, display: "flex", flexDirection: "column", overflow: "hidden" },
        }}
        title={translate("historyList.title")}
        subheader={translate("historyList.selectedElement", {
          element: record.title || record.name || record.id,
        })}
      >
        {/* the events of the element before it must not stay on screen while its
            sibling is inspected */}
        <HistoryList
          key={String(record.id)}
          variant="compact"
          resource={`Historical${resource}`}
          related={resource}
        />
      </SimpleCard>
    </SelectedRecordContextProvider>
  );
};

export default ElementHistory;
