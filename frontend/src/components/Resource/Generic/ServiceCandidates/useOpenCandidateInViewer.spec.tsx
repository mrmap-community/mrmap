import { renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useOpenCandidateInViewer } from "./useOpenCandidateInViewer";

const state = vi.hoisted(() => ({
  addServiceByUrl: vi.fn(),
  resetContext: vi.fn(),
  navigate: vi.fn(),
  token: "secret" as string | undefined,
}));

vi.mock("../../../../react-ows-lib/ContextProvider/OwsContextBase", () => ({
  useOwsContextBase: () => ({
    addServiceByUrl: state.addServiceByUrl,
    resetContext: state.resetContext,
  }),
}));

vi.mock("react-router-dom", () => ({ useNavigate: () => state.navigate }));

vi.mock("../../../../providers/authProvider", () => ({
  getAuthToken: () => (state.token ? { token: state.token } : undefined),
}));

vi.mock("../../../../context/HttpClientContext", () => ({
  API_BASE_URL: "https://mrmap.test/",
}));

beforeEach(() => {
  vi.clearAllMocks();
  state.token = "secret";
});

describe("handing a candidate to the viewer", () => {
  it("appends the endpoint to the current map instead of replacing it", () => {
    const open = renderHook(() => useOpenCandidateInViewer()).result.current;
    open("https://maps.example.org/wms?request=GetCapabilities");
    expect(state.addServiceByUrl).toHaveBeenCalledWith(
      "https://maps.example.org/wms?request=GetCapabilities",
      undefined,
    );
    // the layers the user has on the map stay, which is what the discovery
    // promise of the dialog is about
    expect(state.resetContext).not.toHaveBeenCalled();
    expect(state.navigate).toHaveBeenCalledWith("/viewer");
  });

  it("sends the MrMap token only to the origin which answered the candidate", () => {
    const open = renderHook(() => useOpenCandidateInViewer()).result.current;
    open("https://mrmap.test/proxy/wms/12");
    expect(
      (state.addServiceByUrl.mock.calls[0][1] as Headers).get("Authorization"),
    ).toBe("Token secret");

    open("https://remote.example.org/wms?request=GetCapabilities");
    expect(state.addServiceByUrl.mock.calls[1][1]).toBeUndefined();
  });

  it("asks an anonymous service without credentials", () => {
    state.token = undefined;
    const open = renderHook(() => useOpenCandidateInViewer()).result.current;
    open("https://mrmap.test/proxy/wms/12");
    expect(state.addServiceByUrl).toHaveBeenCalledWith(
      "https://mrmap.test/proxy/wms/12",
      undefined,
    );
  });

  it("treats an url it cannot read as remote", () => {
    const open = renderHook(() => useOpenCandidateInViewer()).result.current;
    open("not a url");
    expect(state.addServiceByUrl.mock.calls[0][1]).toBeUndefined();
    expect(state.navigate).toHaveBeenCalledWith("/viewer");
  });
});
