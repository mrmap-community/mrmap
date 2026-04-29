import {
    Box,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    Stack
} from '@mui/material';
import {
    useListContextWithProps,
    useResourceContext,
    type RaRecord
} from 'ra-core';
import React, { useEffect, useMemo, useState } from 'react';
import { Pagination, SingleFieldList } from 'react-admin';

interface PaginatedSingleFieldListProps<RecordType extends RaRecord = any> {
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
export const PaginatedSingleFieldList = <RecordType extends RaRecord = any>({
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
        <>
            <Stack direction="row" gap={1} flexWrap="wrap">
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
            <Dialog
                open={openModal}
                onClose={() => setOpenModal(false)}
                maxWidth="sm"
                fullWidth
            >
                <DialogTitle>All related {resource} Records</DialogTitle>
                <DialogContent>
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
                </DialogContent>
                <DialogActions>
                    <Button onClick={() => setOpenModal(false)}>Close</Button>
                </DialogActions>
            </Dialog>
        </>
    );
};
