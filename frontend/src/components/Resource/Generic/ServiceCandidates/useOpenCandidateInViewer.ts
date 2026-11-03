import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import {
  API_BASE_URL,
} from "../../../../context/HttpClientContext";
import { getAuthToken } from "../../../../providers/authProvider";
import { useOwsContextBase } from "../../../../react-ows-lib/ContextProvider/OwsContextBase";

/** Whether MrMap credentials may accompany a request to this endpoint. */
const isSameOrigin = (url: string) => {
  try {
    const target = new URL(url);
    return (
      target.hostname === window.location.hostname ||
      target.origin === new URL(API_BASE_URL).origin
    );
  } catch {
    // An url which cannot be read is treated as remote: no credential is sent
    // to something whose origin is unknown.
    return false;
  }
};

/**
 * Adds the endpoint of a candidate to the current map and opens the viewer.
 *
 * This is the handoff of `MapViewerButton` without the registry: the service is
 * not registered, so there is nothing to fetch by id, nothing to route through
 * the Mr. Map proxy and no reason to throw away the layers which are already on
 * the map. `addServiceByUrl` appends a new tree and reads the protocol from the
 * delivered capabilities, which is why the candidate's advertised service is
 * never trusted here.
 *
 * A remote endpoint is asked without credentials, exactly like the backend's own
 * validation does; only the same origin gets the MrMap token.
 */
export const useOpenCandidateInViewer = () => {
  const { addServiceByUrl } = useOwsContextBase();
  const navigate = useNavigate();

  return useCallback(
    (url: string) => {
      const token = getAuthToken()?.token;
      const headers =
        token && isSameOrigin(url)
          ? new Headers({ Authorization: `Token ${token}` })
          : undefined;
      addServiceByUrl(url, headers);
      navigate("/viewer");
    },
    [addServiceByUrl, navigate],
  );
};
