import LayerGroup from 'ol/layer/Group';
import Layer from 'ol/layer/Layer';
import { LayerUtils } from './LayerUtils';

const layerUtils = new LayerUtils();

export class LayerManagerUtils {
  /**
  * @description Updates the layer group object when user moves an element drops it on another node
  * @param nodeBeingDraggedInfo
  */

  public updateLayerGroupOnDrop(nodeInfo:any, layerManagerLayerGroup: LayerGroup): void {
    let dragLayerGroup;
    let dropLayerGroup;
 
    // checks if the layer is being inserted between two nodes of the same level or as a new layer
    // of another node root level
    const isDroppingToGap = nodeInfo.dropToGap;
    // Information about the layer being dragged
    const dragLayer = layerUtils.getLayerByMrMapLayerId(layerManagerLayerGroup, nodeInfo.dragNode.key);
    dragLayerGroup = layerUtils.getLayerByMrMapLayerId(layerManagerLayerGroup, dragLayer?.getProperties().parent);
   
    // if parent is null, no layer will be found, meaning the group to drop is the defined root group
    if(!dragLayerGroup) {
      dragLayerGroup = layerManagerLayerGroup;
    }
   
    // Information about the target layer/layer group
    const dropLayer = layerUtils.getLayerByMrMapLayerId(layerManagerLayerGroup, nodeInfo.node.props.eventKey);
    if(isDroppingToGap) {
      dropLayerGroup = layerUtils.getLayerByMrMapLayerId(layerManagerLayerGroup, dropLayer?.getProperties().parent);
    } else {
      dropLayerGroup = layerUtils.getLayerByMrMapLayerId(layerManagerLayerGroup, dropLayer?.getProperties().key);
    }
   
    // if parent is null, no layer will be found, meaning the group to drop is the defined root group
    if(!dropLayerGroup) {
      dropLayerGroup = layerManagerLayerGroup;
    }
 
    // the postion where to insert
    const postionToInsert = dropLayerGroup.getLayersArray().indexOf(dropLayer as Layer<any>);
 
    // remove layer from dragLayerGroup (the group where the layer was set originally)
    if(dragLayer && dragLayerGroup && dragLayerGroup instanceof LayerGroup) {
      dragLayerGroup.getLayers().remove(dragLayer);
    }
   
    // // add the layer to its new position
    if(dragLayer && dropLayer && dropLayerGroup && dropLayerGroup instanceof LayerGroup) {
      // place to insert needs to be right after the dropLayer
      dragLayer.set('parent', dropLayerGroup.getProperties().key);
      dropLayerGroup.getLayers().insertAt(postionToInsert + 1, dragLayer);
    }
  }

}
