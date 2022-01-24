import Collection from 'ol/Collection';
import BaseLayer from 'ol/layer/Base';
import LayerGroup from 'ol/layer/Group';
import ImageLayer from 'ol/layer/Image';
import ImageWMS from 'ol/source/ImageWMS';
import { CreateLayerOpts } from '../Components/LayerManager/LayerManagerTypes';
import { MPTTJsonApiTreeNodeType, TreeNodeType } from '../Components/Shared/FormFields/TreeFormField/TreeFormFieldTypes';
import { LayerUtils } from './LayerUtils';

const layerUtils = new LayerUtils();

export class TreeUtils {
  public OlLayerGroupToTreeNodeList(layerGroup: LayerGroup): TreeNodeType[] {
    
    return layerGroup.getLayers().getArray().map((layer: LayerGroup | BaseLayer) => {
      const node: any = {
        key: layer.getProperties().layerId,
        title: layer.getProperties().description,
        parent: layer.getProperties().parent,
        properties: layer.getProperties(),
        isLeaf: true,
        expanded: layer instanceof LayerGroup,
        children: []
      }; 
      if (layer instanceof LayerGroup ) {
        node.children = this.OlLayerGroupToTreeNodeList(layer);
        node.isLeaf = false;
      }
      return node;
    });
  }

  /**
  * @description: Method to parse an MPTT tree array to a TreeNodeType array
    * @param list
    * @returns
    */
  private MPTTListToTreeNodeList(list:MPTTJsonApiTreeNodeType[]):TreeNodeType[] {
    const roots:TreeNodeType[] = [];
  
    // initialize children on the list element
    list = list.map((element: MPTTJsonApiTreeNodeType) => ({ ...element, children: [] }));
  
    list.map((element:MPTTJsonApiTreeNodeType) => {
      // transform the list element into a TreeNodeType element

      // NOTE: on the backend, we have no way to check if the layer is a leaf.
      // Adding a flag is not desirable, since it will currupt the data structure of a MapContextLayer.
      // So, we are checking only if the node has children or not. If it has children,
      // then, it's because the node is a group, otherwise, is a leaf
      const node: TreeNodeType = {
        key: element.id,
        title: element.attributes.description,
        parent: element.relationships.parent.data?.id,
        children: element.children || [],
        isLeaf: element.children && element.children.length === 0,
        properties: {
          title: element.attributes.title, // yes, title is repeated
          description: element.attributes.description,
          datasetMetadata: element.relationships.dataset_metadata.data?.id,
          renderingLayer: element.relationships.rendering_layer.data?.id,
          scaleMin: element.attributes.layer_scale_min,
          scaleMax: element.attributes.layer_scale_max,
          style: element.relationships.layer_style.data?.id,
          featureSelectionLayer: element.relationships.selection_layer.data?.id,
        },
        expanded: true
      };
    
      if (node.parent) {
        const parentNode: MPTTJsonApiTreeNodeType | undefined = list.find((el:any) => el.id === node.parent);
        if (parentNode) {
          list[list.indexOf(parentNode)].children?.push(node);
        }
      } else {
        roots.push(node);
      }
      return element;
    });
    return roots;
  }
  
  private TreeNodeListToOlLayerGroup(list: TreeNodeType[]): Collection<LayerGroup | ImageLayer<ImageWMS>> {
    const layerList = list.map((node: TreeNodeType) => {
      if (node.children.length > 0) {
        const layerGroupOpts = {
          opacity: 1,
          visible: false,
          properties: {
            title: node.properties.title,
            description: node.properties.description,
            parent: node.parent,
            key: node.key,
            layerId: node.key
          },
          layers: this.TreeNodeListToOlLayerGroup(node.children)
        };
        return new LayerGroup(layerGroupOpts);
      } 
  
      if(node.children.length === 0) {
        const layerOpts: CreateLayerOpts = {
          url: '',
          version: '1.1.0',
          format: 'image/png',
          layers: '',
          serverType: 'MAPSERVER',
          visible: false,
          legendUrl: '',
          title: node.properties.title,
          description: node.properties.description,
          layerId: node.key,
          properties: {
            ...node.properties,
            parent: node.parent,
            key: node.key,
          }
        };
        return layerUtils.createMrMapOlWMSLayer(layerOpts);
      }
      return new LayerGroup();
    });
    return new Collection(layerList);
  }
  
  public MPTTListToOLLayerGroup(list:MPTTJsonApiTreeNodeType[]): Collection<LayerGroup | BaseLayer> {
    if(list) {
      const treeNodeList = this.MPTTListToTreeNodeList(list);
      const layerGroupList = this.TreeNodeListToOlLayerGroup(treeNodeList);
      return layerGroupList;
    }
    return new Collection();
  }

  /**
   * @description Method that runs through the tree and updates the children of a specific node
   * @param list
   * @param key
   * @param children
   * @returns TreeNodeType[]
   */
   public updateTreeData(list: TreeNodeType[], key?: React.Key, children?: TreeNodeType[]): TreeNodeType[] {
    return list.map(node => {
      if(key && children){
        if (node.key === key) {
          return {
            ...node,
            children
          };
        }
        if (node.children) {
          return {
            ...node,
            children: this.updateTreeData(node.children, key, children)
          };
        }
        return node;
      } else {
        return node;
      }
    });
  }

  /**
   * @description Method that finds the parent node of a given node
   * @param list
   * @param node
   * @returns TreeNodeType[] | never[]
   */
  public getNodeParent(list: TreeNodeType[], node: TreeNodeType): TreeNodeType[] | never[]{ 
    return list.flatMap((value: TreeNodeType) => {
      if (value.key === node.parent) {
        return value;
      }
      if (value.children) {
        return this.getNodeParent(value.children, node);
      }
      return value;
    });
  }

}
