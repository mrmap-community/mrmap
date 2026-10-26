import React, { Fragment, useEffect, useMemo, useState } from 'react';
import { Pagination, SingleFieldList } from 'react-admin';

import {
  Box,
  Button,
  Stack
} from '@mui/material';
import {
  useListContextWithProps,
  useResourceContext,
  type RaRecord
} from 'ra-core';

import ContextBasedDialog from '../../components/Dialog/Dialog';
import DialogHeader from '../../components/Dialog/DialogHeader';

interface PaginatedSingleFieldListProps<RecordType extends RaRecord = RaRecord> {
    visibleCount?: number;
    children?: React.ReactNode;
    data?: RecordType[];
    total?: number;
    loaded?: boolean;
}

/**
 * Enhanced SingleFieldList that shows only X records with a "show more" button
 * Opens a modal with all records when clicked
 */
export const PaginatedSingleFieldList = <RecordType extends RaRecord = RaRecord>({
    visibleCount = 3,
    children,
    ...props
}: PaginatedSingleFieldListProps<RecordType>) => {
    const [openModal, setOpenModal] = useState(false);
    const { data, total } = useListContextWithProps(props);
    const [visibleData, setVisibleData] = useState<RaRecord[]>()
    
    const hiddenCount = useMemo(()=> ((total ?? 0) - visibleCount), [total])
    const resource = useResourceContext()

    useEffect(()=>{
        if (data !== undefined && visibleData === undefined){
            setVisibleData(data.slice(0, visibleCount))
        }
    },[data, visibleData])

    return (
        <Fragment>
            <Stack direction="row" sx={{ gap: 1, flexWrap: "wrap" }}>
                <SingleFieldList
                  data={visibleData}
                />
                
                {hiddenCount > 0 && (
                    <Button
                        size="small"
                        variant="outlined"
                        onClick={() => setOpenModal(true)}
                        sx={{ textTransform: 'none' }}
                    >
                        +{hiddenCount} more
                    </Button>
                )}
            </Stack>

            {/* Modal to show all records */}
            <ContextBasedDialog
                open={openModal}
                onClose={() => setOpenModal(false)}
                maxWidth="sm"
                fullWidth
                contentDividers={false}
                title={
                    <DialogHeader onClose={() => setOpenModal(false)}>
                        All related {resource} Records
                    </DialogHeader>
                }
                actions={<Button onClick={() => setOpenModal(false)}>Close</Button>}
                actionsAlign="flex-end"
            >
                    <Box sx={{ pt: 2 }}>
                        <SingleFieldList
                            data={data}
                            total={total}
                            loaded={true}
                            
                        >
                            {children}
                        </SingleFieldList>
                        <Pagination/>
                    </Box>
            </ContextBasedDialog>
        </Fragment>
    );
};
