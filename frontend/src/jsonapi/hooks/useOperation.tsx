import { useMemo } from "react";
import { type Operation } from "openapi-client-axios";
import { useHttpClientContext } from "../../context/HttpClientContext";

const useOperation = (
  operationId: string | undefined,
): Operation | undefined => {
  const { api } = useHttpClientContext();
  return useMemo(
    () => (operationId ? api?.getOperation(operationId) : undefined),
    [api, operationId],
  );
};

export default useOperation;
