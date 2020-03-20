# Functionality
The system provides the following functionalities:

* User management
  * Create users and organize them in groups, supporting group hierarchy 
  * Configure group inherited permissions
  * Organize groups in organizations 
* Service management
  * Register web map services in all current versions (1.0.0 - 1.3.0)
  * Register web feature services in all current versions (1.0.0 - 2.0.2)
  * Create automatically organizations from service metadata
  * Generate Capabilities links to use in any map viewer which supports WMS/WFS imports
* Metadata Editor 
  * Edit describing service metadata such as titles, abstracts, keywords and so on
  * Edit describing metadata for every subelement such as map layers or feature types
  * Reset metadata on every level of service hierarchy
* Proxy
  * Mask service related links using an internal proxy 
     * tunnels `GetCapabilities` requests, `LegendURL`, `MetadataURL`, `GetMap`, `GetFeature` and more
* Secured Access
  * Restrict access to your service (public/private)
  * Allow access for certain groups of users
  * Draw geometries to allow access only in these spatial areas
* Publisher system
  * Allow other groups to register your services with reference on your organization
  * Revoke the permissions whenever you want 
* Dashboard
  * Have an overview on all newest activities of your groups, all your registered services or 
  pending publisher requests
* Catalogue and API
  * Find services using the catalogue JSON interface 
  * Have reading access to metadata, whole services, layers, organizations or groups
