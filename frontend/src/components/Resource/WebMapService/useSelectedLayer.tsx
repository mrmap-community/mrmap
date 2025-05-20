import { useCallback, useMemo } from 'react';
import { Identifier } from 'react-admin';
import { useSearchParams } from 'react-router-dom';


const useSelectedLayer = (
  initSelectedLayer?: Identifier, 
): [string | null, (layerId: string) => void] => {
  
  const [searchParams, setSearchParams] = useSearchParams(initSelectedLayer ? [["selectedLayer", String(initSelectedLayer)]]: []);
  const selectedLayer = useMemo(()=> searchParams.get("selectedLayer") ?? null, [searchParams])
  
  const setSelectedLayer = useCallback((layerId: string) => {
    searchParams.set("selectedLayer", layerId);
    setSearchParams(searchParams)
  },[searchParams, setSearchParams])

  return [selectedLayer, setSelectedLayer]
}

export default useSelectedLayer
