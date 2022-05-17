import OgcServiceDetails from "@/components/RessourceDetails/OgcServiceDetails";
import type { JsonApiDocument, JsonApiPrimaryData } from "@/utils/jsonapi";
import { getIncludesByType } from "@/utils/jsonapi";
import type { ParamsArray } from "openapi-client-axios";
import type { ReactElement } from "react";


interface Node {
    key: any;
    raw: JsonApiPrimaryData;
    title: string;
    isLeaf: boolean
}

const transformTreeData = (wfs: JsonApiDocument): Node[] => {
    return getIncludesByType(wfs, 'FeatureType').map((node) => {
        return {
            key: node.id, 
            title: node.attributes.stringRepresentation, 
            raw: node,
            isLeaf: true,
        }
    });
    
};

const WfsDetails = (): ReactElement => {


    /**
     * derived constants
     */
     const getWebFeatureServiceParams: ParamsArray = [
        {
            in: 'query',
            name: 'include',
            value: 'featuretypes',
        },
        {
            in: 'query',
            name: 'fields[FeatureType]',
            value: 'string_representation,is_active,dataset_metadata'
        }
    ];


    return (
        <OgcServiceDetails
            resourceType='WebFeatureService'
            additionalGetRessourceParams={getWebFeatureServiceParams}
            nodeRessourceType={"FeatureType"}
            transformTreeData={transformTreeData}
        />
    );

};


export default WfsDetails;
