import type { Middleware } from "ra-core";

import { FormProvider, useForm } from "react-hook-form";

import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReferenceManyInput } from "./ReferenceManyInput";

const state = vi.hoisted(() => ({
  middleware: undefined as Middleware | undefined,
  create: vi.fn(),
  update: vi.fn(),
  record: { id: 7, children: [{ id: 9, stringRepresentation: "Child" }] },
}));
vi.mock("ra-core", async importOriginal => ({
  ...await importOriginal<typeof import("ra-core")>(),
  useCreate: () => [state.create],
  useUpdate: () => [state.update],
  useInfiniteGetList: () => ({ isFetched: false }),
  useRecordContext: () => state.record,
  useResourceContext: () => "Parent",
  useLocation: () => ({ state: undefined }),
  useNavigate: () => vi.fn(),
  useRegisterMutationMiddleware: (middleware: Middleware) => { state.middleware = middleware; },
}));
vi.mock("react-admin", async importOriginal => ({
  ...await importOriginal<typeof import("react-admin")>(),
  ArrayInput: () => null,
}));
vi.mock("../hooks/useFieldsForOperation", () => ({ useFieldsForOperation: () => [] }));
vi.mock("./ReferenceManyErrorsProvider", () => ({ useReferenceManyErrors: () => ({ addErrors: vi.fn() }) }));

const Form = () => {
  const form = useForm();
  return <FormProvider {...form}><ReferenceManyInput reference="Child" source="children" target="parent" /></FormProvider>;
};

beforeEach(() => {
  state.middleware = undefined;
  state.create.mockReset();
  state.update.mockReset().mockResolvedValue({ id: 9 });
});

describe("nested mutation middleware", () => {
  // react-admin v5 invokes registered middlewares as (resource, params, next), where `next`
  // runs the rest of the chain and finally the data provider function, resolving to the
  // provider's result envelope { data: record }. With the former v4 signature
  // (resource, params, options, next) the middleware received undefined as `next` and threw
  // before any request was sent (#1198), so these specs call it the way ra-core does.
  it("links nested records to the parent record returned through the v5 (resource, params, next) call", async () => {
    render(<Form />);
    await waitFor(() => expect(state.middleware).toBeTypeOf("function"));
    const parent = { data: { id: 7, title: "Saved parent" } };
    const next = vi.fn().mockResolvedValue(parent);
    const params = { data: { title: "Saved parent" } };
    const result = await state.middleware!("Parent", params, next);
    expect(next).toHaveBeenCalledWith("Parent", params);
    expect(state.update).toHaveBeenCalledWith("Child", {
      id: 9,
      data: { id: 9, stringRepresentation: "Child", parent: { id: 7 } },
      previousData: { id: 9, stringRepresentation: "Child" },
    }, { returnPromise: true });
    expect(result).toBe(parent);
  });
  it("does not save children when the parent mutation fails", async () => {
    render(<Form />);
    await waitFor(() => expect(state.middleware).toBeTypeOf("function"));
    const error = new Error("Parent rejected");
    const next = vi.fn().mockRejectedValue(error);
    await expect(state.middleware!("Parent", { data: {} }, next)).rejects.toBe(error);
    expect(state.create).not.toHaveBeenCalled();
    expect(state.update).not.toHaveBeenCalled();
  });
});
