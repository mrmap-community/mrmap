import { createElement, type ComponentType, type ReactNode } from "react";
import type { ButtonProps, RaRecord } from "react-admin";
import {
  RecordContextProvider,
  useGetOne,
  useResourceContext,
  useTranslate,
} from "react-admin";

import { LinearProgress, Typography } from "@mui/material";

import { useSelectedRecordContext } from "../../../../jsonapi/components/SelectedRecordContext";
import SimpleCard from "../../../MUI/SimpleCard";
import WfsViewerButtons from "../../WebFeatureService/Button/ListActions";
import WmsViewerButtons from "../../WebMapService/Button/ListActions";

/** What the buttons of a service are asked to show: the element and the size they answer it in. */
interface ElementViewerButtonsProps {
  element?: RaRecord;
  size?: ButtonProps["size"];
}

/** The service which owns an element, and the buttons which open that service in the viewer. */
const SERVICE_OF_ELEMENT: Record<
  string,
  { resource: "WebMapService" | "WebFeatureService"; buttons: ComponentType<ElementViewerButtonsProps> }
> = {
  Layer: { resource: "WebMapService", buttons: WmsViewerButtons },
  FeatureType: { resource: "WebFeatureService", buttons: WfsViewerButtons },
};

/**
 * The map viewer button of the layer or feature type a screen of elements has selected.
 *
 * The click of the list names the element; the card asks the service which owns it and hands both to
 * the buttons which open that service in the viewer - the same buttons a row of the service lists
 * offers, so a secured service is answered by its secured document and an unsecured one by its
 * stored operations. The selected element is the one the viewer activates, which is what lets the
 * whole document of the service be opened with exactly the clicked layer or feature type on the map.
 * Without a click there is nothing to show, and the card names the click which would answer it.
 */
const SelectedElementViewerCard = (): ReactNode => {
  const { selectedRecord: element } = useSelectedRecordContext();
  const resource = useResourceContext();
  const translate = useTranslate();

  const service = SERVICE_OF_ELEMENT[resource ?? ""];
  const serviceId = element?.service?.id as string | undefined;
  const {
    data: serviceRecord,
    isPending,
    error,
  } = useGetOne(
    service?.resource ?? "WebMapService",
    { id: serviceId },
    // a screen which lists neither layers nor feature types asks nothing, and neither does a row
    // which names no service
    { enabled: service !== undefined && serviceId !== undefined },
  );

  return (
    <SimpleCard
      title={translate("ra.action.mapviewer")}
      cardProps={{ variant: "outlined", sx: { width: "100%", height: "auto" } }}
      footer={
        // the buttons read their service from the record context, the way a row of the service
        // lists hands it to them
        service === undefined || serviceRecord === undefined ? undefined : (
          <RecordContextProvider value={serviceRecord}>
            {createElement(service.buttons, { element, size: "small" })}
          </RecordContextProvider>
        )
      }
    >
      {element === undefined ? (
        <Typography variant="body2" color="text.secondary">
          {translate("layerInspection.select")}
        </Typography>
      ) : service === undefined || serviceId === undefined ? null : (
        <>
          <Typography variant="body2" color="text.secondary">
            {translate("serviceShow.mapViewerOfElement")}
          </Typography>
          {isPending ? (
            <LinearProgress sx={{ mt: 1 }} />
          ) : error !== undefined ? (
            <Typography variant="body2" color="text.error" sx={{ mt: 1 }}>
              {translate("ra.notification.http_error")}
            </Typography>
          ) : null}
        </>
      )}
    </SimpleCard>
  );
};

export default SelectedElementViewerCard;
