import { useQuery } from "@tanstack/react-query";

import {
  API_BASE_URL,
  useHttpClientContext,
} from "../../../../context/HttpClientContext";
import useOperation from "../../../../jsonapi/hooks/useOperation";
import { getAuthToken } from "../../../../providers/authProvider";

/**
 * Attributes of these answers are spelled in snake_case.
 *
 * The resolution actions answer plain json of the backend's dataclasses — like
 * the live preview actions they mirror — and not a json:api resource, which
 * the data provider would have camelized. The keys below are therefore the
 * contract of the action, not a naming decision of the frontend.
 */
export type CandidateState =
  | "unvalidated"
  | "resolved"
  | "ambiguous"
  | "unsupported"
  | "unavailable";

export type CandidateSource =
  | "own-distribution"
  | "own-operation"
  | "coupled-service-record"
  | "metadata-reference-record";

/** One advertised possibility to access what the record describes. */
export interface ServiceCandidate {
  /** The capabilities endpoint to ask; may equal the advertised url. */
  url: string;
  original_url: string;
  /** What the advertised url itself is: capabilities or an operation. */
  kind: string;
  source: CandidateSource;
  state: CandidateState;
  detail?: string;
  protocol?: string | null;
  /** The ogc service token, e.g. WMS or WFS. */
  service?: string | null;
  advertised_version?: string | null;
  operation?: string | null;
  /** Feature type hints of the record, kept apart from the url. */
  type_names?: string[];
  /** Layer hints of the record, kept apart from the url. */
  layers?: string[];
  /** The single best candidate of the whole answer. */
  preferred?: boolean;
  /** Why this candidate belongs to the record. */
  evidence?: string[];
  /** Whether the capabilities url was derived from an operation url. */
  derived?: boolean;
}

/** A registered resource which a stored relation already verified. */
export interface RegisteredTarget {
  resource_type: "wms" | "wfs" | "csw";
  id: number;
  name: string;
  service_id?: number | null;
}

/** The discovery answer of one metadata record. */
export interface RecordResolution {
  status: "ok" | "missing" | "unreadable" | "malformed" | "no_records";
  detail?: string;
  file_identifier?: string | null;
  service_type?: string | null;
  service_type_version?: string | null;
  candidates: ServiceCandidate[];
  registered_targets: RegisteredTarget[];
  /** Links which advertise something, but no service access. */
  non_service_links?: Record<string, unknown>[];
  /** Whether a budget cut the lookup; the answer may hold more. */
  truncated?: boolean;
  warnings?: string[];
}

/** The answer of asking one advertised endpoint. */
export interface CandidateValidation {
  state: CandidateState;
  /** Machine readable reason, e.g. `exception-report:OperationNotSupported`. */
  detail?: string;
  service_type?: string | null;
  service_version?: string | null;
  advertised_names?: string[];
  /** Hints of the record the endpoint confirmed. */
  matched_names?: string[];
  /** Hints of the record the endpoint could not confirm. */
  unresolved_hints?: string[];
  names_truncated?: boolean;
}

/** The reason an action gave, so the screen can name it instead of "error". */
export class CandidateFailure extends Error {
  constructor(public code: string) {
    super(code);
  }
}

/**
 * Performs one of the plain json resolution actions of a metadata record.
 *
 * Mirrors `usePreview`, which is the house pattern for an action that is not a
 * json:api resource: the url comes from the schema operation, only the same
 * origin gets the MrMap token and every answer keeps its own error code. The
 * actions answer `application/json`, so that is what they are asked for — the
 * data provider's default `application/vnd.api+json` is refused with a 406.
 */
const useMetadataResolution = <Response,>(
  operationId: string,
  parameters: Record<string, string>,
  enabled: boolean,
  key: unknown[],
) => {
  const { api } = useHttpClientContext();
  const operation = useOperation(operationId);
  const query = useQuery<Response, CandidateFailure>({
    queryKey: ["metadataResolution", ...key],
    enabled: enabled && Boolean(api && operation),
    retry: false,
    gcTime: 0,
    staleTime: 0,
    queryFn: async ({ signal }) => {
      if (!api) throw new DOMException("Aborted", "AbortError");
      const config = api.getAxiosConfigForOperation(operationId, [
        parameters,
        undefined,
        { signal },
      ]);
      const endpoint = new URL(
        config.url ?? "",
        config.baseURL ?? API_BASE_URL,
      );
      if (endpoint.origin !== new URL(API_BASE_URL).origin)
        throw new CandidateFailure("denied");
      const token = getAuthToken()?.token;
      config.headers = {
        Accept: "application/json",
        ...(token ? { Authorization: `Token ${token}` } : {}),
      };
      try {
        const response = await api.client.request<Response>(config);
        if (signal.aborted) throw new DOMException("Aborted", "AbortError");
        return response.data;
      } catch (error) {
        if (signal.aborted) throw error;
        const response = (
          error as {
            response?: { status?: number; data?: { error?: string } };
          }
        ).response;
        throw new CandidateFailure(
          response?.data?.error ??
            (response?.status === 403 || response?.status === 401
              ? "denied"
              : "unavailable"),
        );
      }
    },
  });
  return { ...query, supported: Boolean(operation) };
};

/**
 * Which services can deliver the record, without asking any of them.
 *
 * Discovery reads the stored document of the record and the coupling index of
 * the registry; it performs no upstream request, so it is cheap enough to run
 * when the screen asks for it.
 */
export const useServiceCandidates = (
  resource: string | undefined,
  id: string | undefined,
  enabled = true,
) =>
  useMetadataResolution<RecordResolution>(
    `service_candidates_${resource}`,
    { id: id ?? "" },
    enabled && Boolean(resource && id),
    [resource, id],
  );

/**
 * Asks the one endpoint the user selected, once.
 *
 * The backend refuses an url the record never advertised before it performs a
 * request, so the selected candidate has to be the answered one and a refused
 * call costs nothing.
 */
export const useValidateServiceCandidate = (
  resource: string | undefined,
  id: string | undefined,
  url: string | undefined,
  enabled = true,
) =>
  useMetadataResolution<CandidateValidation>(
    `validate_service_candidate_${resource}`,
    { id: id ?? "", url: url ?? "" },
    enabled && Boolean(resource && id && url),
    [resource, id, url],
  );
