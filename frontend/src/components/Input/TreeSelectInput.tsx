import { Chip, FormControl, FormHelperText, FormLabel, Paper } from '@mui/material';
import { SimpleTreeView, TreeItem } from "@mui/x-tree-view";
import { useMemo } from "react";
import { Identifier, Loading, RaRecord, TextFieldProps, useGetOne, useInput } from "react-admin";
import { useFormContext, } from "react-hook-form";
import { getDescendants } from '../MapViewer/utils';
import { getSubTree } from "../utils";
export interface TreeSelectInputProps extends TextFieldProps{
  wmsId: Identifier
}



const TreeSelectInput = ({
  wmsId,
  source,
  ...props  
}: TreeSelectInputProps) => {
  const { className, emptyText, ...rest } = props;

  const {setValue} = useFormContext();
  const { data: record, isPending } = useGetOne(
    'WebMapService',
    { id: wmsId , meta: {jsonApiParams: {include: 'layers'}} },
    
);
  const layerListPreOrderd = useMemo<RaRecord[]>(()=>record?.layers.sort((a: RaRecord, b: RaRecord) => a.mpttLft > b.mpttLft) || [], [record?.layers])
  
  const tree = useMemo(()=> getSubTree(layerListPreOrderd), [layerListPreOrderd]);
  
  const { id, field: {value}, fieldState: {invalid }, formState, isRequired} = useInput(
    { 
      source: source, 
      isRequired: rest.isRequired,
      defaultValue: []
    }
  );

  const selectedItems = useMemo<string[]>((
    ) => 
      Array.isArray(value) && 
      value?.map((r: RaRecord) => r?.id?.toString()).filter((id: string) => id !== undefined) || [], [value])
   
  return (

      <FormControl
        disabled={layerListPreOrderd.length === 0}
        error={invalid}
      >
      <FormLabel htmlFor={`${id}-input`} required={isRequired}>
        {rest.label }

        <Chip
          size="small"
          variant="filled"
          label={`${selectedItems.length} selected`}
          sx={{marginLeft: 1, marginBottom: 1}}
        />
        
      </FormLabel>

      <Paper
        id={`${id}-input`}
        aria-describedby={`${id}-text`}
      >
      {wmsId && isPending ? <Loading loadingSecondary='loading layers'/>: null}
        <SimpleTreeView
          multiSelect
          checkboxSelection
          selectedItems={selectedItems}
          onItemSelectionToggle={(event: React.SyntheticEvent, itemId: string, isSelected: boolean) => {
            const node = layerListPreOrderd.find((r: RaRecord) => r.id === itemId)
            const children = getDescendants(layerListPreOrderd, node, true).map((r: RaRecord) => r?.id?.toString())
            if (isSelected){
              setValue(source, [...new Set([...selectedItems, ...children])].map(id => ({id: id})), { shouldDirty: true })
            } else {
              setValue(source, selectedItems.filter((itemId: string) => !children.includes(itemId)).map(id => ({id: id})), { shouldDirty: true })
            }

          }}
          disableSelection= {layerListPreOrderd.length === 0}
          
        > 
        
          {layerListPreOrderd.length > 0 ? tree : <TreeItem  itemId='empty-tree' label={'...'}/>}
        </SimpleTreeView> 
        </Paper>
      <FormHelperText id={`${id}-text`}>{invalid || rest.helperText}</FormHelperText>
      </FormControl>
  )
};

export default TreeSelectInput;