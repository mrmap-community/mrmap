import type { PropsWithChildren } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  useServiceCandidates,
  useValidateServiceCandidate,
} from "./useServiceCandidates";

const state = vi.hoisted(() => ({
  request: vi.fn(),
  asked: undefined as string | undefined,
  endpoint: "https://mrmap.test/api/registry/dataset-metadata/record/service-candidates",
}));

vi.mock("../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "https://mrmap.test",
  useHttpClientContext: () => ({
    api: {
      // the schema knows the resolution actions of the metadata resources only
      getOperation: () => ({}),
      getAxiosConfigForOperation: (
        operationId: string,
        [params, , options]: [object, unknown, object],
      ) => {
        state.asked = operationId;
        return { url: state.endpoint, params, ...options };
      },
      client: { request: state.request },
    },
  }),
}));

vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => ({ token: "secret" }),
}));

const wrapper = ({ children }: PropsWithChildren) => (
  <QueryClientProvider
    client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
  >
    {children}
  </QueryClientProvider>
);

beforeEach(() => {
  vi.clearAllMocks();
  state.asked = undefined;
  state.endpoint =
    "https://mrmap.test/api/registry/dataset-metadata/record/service-candidates";
});

describe("the discovery of the candidates of a record", () => {
  it("asks the schema action of the metadata resource for plain json", async () => {
    state.request.mockResolvedValue({
      data: { status: "ok", candidates: [], registered_targets: [] },
    });
    const hook = renderHook(
      () => useServiceCandidates("DatasetMetadataRecord", "record-1"),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.isSuccess).toBe(true));
    expect(state.asked).toBe("service_candidates_DatasetMetadataRecord");
    const config = state.request.mock.calls[0][0];
    expect(config.params).toEqual({ id: "record-1" });
    // the action mirrors the preview actions: it refuses the json:api media type
    expect(config.headers.Accept).toBe("application/json");
    expect(config.headers.Authorization).toBe("Token secret");
    expect(hook.result.current.data?.candidates).toEqual([]);
    hook.unmount();
  });

  it("asks nothing while the dialog which offers it is closed", async () => {
    const hook = renderHook(
      () => useServiceCandidates("DatasetMetadataRecord", "record-1", false),
      { wrapper },
    );
    expect(state.request).not.toHaveBeenCalled();
    expect(hook.result.current.supported).toBe(true);
    hook.unmount();
  });

  it("keeps MrMap credentials away from an origin the schema does not answer with", async () => {
    state.endpoint = "https://unrelated.test/service-candidates";
    const hook = renderHook(
      () => useServiceCandidates("ServiceMetadataRecord", "record-2"),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.error?.code).toBe("denied"));
    expect(state.request).not.toHaveBeenCalled();
    hook.unmount();
  });

  it("refuses to validate an endpoint before one is selected", async () => {
    const hook = renderHook(
      () => useValidateServiceCandidate("DatasetMetadataRecord", "record-1", undefined),
      { wrapper },
    );
    expect(state.request).not.toHaveBeenCalled();
    hook.unmount();
  });

  it("names the reason the api gave for refusing an endpoint", async () => {
    state.endpoint =
      "https://mrmap.test/api/registry/dataset-metadata/record/validate-service-candidate";
    state.request.mockRejectedValue({
      response: { status: 422, data: { error: "not-advertised" } },
    });
    const hook = renderHook(
      () =>
        useValidateServiceCandidate(
          "DatasetMetadataRecord",
          "record-1",
          "https://other.example.org/wms",
        ),
      { wrapper },
    );
    await waitFor(() => expect(hook.result.current.error?.code).toBe("not-advertised"));
    expect(state.asked).toBe(
      "validate_service_candidate_DatasetMetadataRecord",
    );
    expect(state.request.mock.calls[0][0].params).toEqual({
      id: "record-1",
      url: "https://other.example.org/wms",
    });
    hook.unmount();
  });
});
