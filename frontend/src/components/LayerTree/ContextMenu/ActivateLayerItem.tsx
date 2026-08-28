import PowerIcon from '@mui/icons-material/Power';
import { useEffect } from 'react';
import { useListContext, useRecordContext, useTranslate, useUpdate } from 'react-admin';
import { useContextMenuBase } from "./ContextMenuBase";
import ContextMenuItem from './ContextMenuItem';


const ActivateLayerItem = () => {
  const translate = useTranslate();
  const { close } = useContextMenuBase()
  const record = useRecordContext()
  const { refetch } = useListContext(); 

  const [update, { isSuccess }] = useUpdate("Layer", {id: record?.id, data:{isActive: !record?.isActive}, previousData: record});


  useEffect(()=>{
    if (isSuccess){
      refetch()
      close()
    }
  },[isSuccess])

  return (
    <ContextMenuItem
      onClick={()=>update()}
      icon={<PowerIcon fontSize="small" />}
      label={translate('LayerTree.ContextMenu.activateLayer')}
    />
  )
}


export default ActivateLayerItem