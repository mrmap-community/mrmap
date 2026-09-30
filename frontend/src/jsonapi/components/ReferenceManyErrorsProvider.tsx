import {
  createContext,
  PropsWithChildren,
  useCallback,
  useContext,
  useRef,
} from 'react';
import { RaRecord } from 'react-admin';

export interface ReferenceManyError {
    source: string;
    index: number;
    record: RaRecord;
    errors: Record<string, { message: string }>;
}

type ReferenceManyErrorsContextValue = {
    addErrors: (errors: ReferenceManyError[]) => void;
    getErrors: () => ReferenceManyError[];
    clearErrors: () => void;
};

const ReferenceManyErrorsContext =
    createContext<ReferenceManyErrorsContextValue | undefined>(undefined);

export const ReferenceManyErrorsProvider = ({
    children,
}: PropsWithChildren) => {
    const errorsRef = useRef<ReferenceManyError[]>([]);

    const addErrors = useCallback((errors: ReferenceManyError[]) => {
        errorsRef.current = [
            ...errorsRef.current,
            ...errors,
        ];
    }, []);

    const getErrors = useCallback(
        () => errorsRef.current,
        []
    );

    const clearErrors = useCallback(() => {
        errorsRef.current = [];
    }, []);

    return (
        <ReferenceManyErrorsContext.Provider
            value={{
                addErrors,
                getErrors,
                clearErrors,
            }}
        >
            {children}
        </ReferenceManyErrorsContext.Provider>
    );
};

export const useReferenceManyErrors = () => {
    const context = useContext(ReferenceManyErrorsContext);

    if (!context) {
        throw new Error(
            'useReferenceManyErrors must be used inside ReferenceManyErrorsProvider'
        );
    }

    return context;
};