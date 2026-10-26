# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.x.x] - UNRELEASED

### Added
- Cross-service attention list, app-bar count and dashboard card for service failures, update reviews and overdue schedules (#567).
- Alerts of a service answer which monitoring run, update job or harvesting job decided them, and the attention tab of a service links to that record (#596).
- The aside of a screen of services answers the selected service first: its states which need attention, the outcome of its last monitoring run and update job and a direct way to its screen (#597).
- Work queue card on the dashboard which counts the alerts, the update reviews and the running and failed background work of everything the user may see, and links to the list of those very records (#601).
- The capabilities document of a stored WMS or WFS publishes the dataset coupling a curator maintains in MrMap: a curated relation of a layer or feature type adds a metadata reference which points to the iso record of the linked dataset, beside the references which were imported with the document (#674).
- Per layer opacity in the map viewer: the layer settings panel blends a layer between invisible and fully drawn in five percent steps, keeps the value for the viewer session, and asks for a map of its own as soon as two layers differ, so the blending of one layer never dims another; a feature layer dims its outlines, fills and point symbols together (#750).

### Changed
- The system status of the app bar stops polling `/api/system/status/current` while the MrMap tab is hidden and refreshes the displayed status as soon as the user returns (#749).
- The browsable REST API is a development facility only; a production deployment (`MRMAP_PRODUCTION=True`) registers no browsable renderer, so an HTML-only request is answered with the usual content negotiation rejection and requests without an `Accept` header receive the JSON:API representation (#751).
- A metadata reference of an imported capabilities document is published as it was imported and is removed only if the database does not know its link anymore; a reference which holds no online resource is no longer published, because it is not valid xml (#674).
- building docs with readthedocs.org instead of using custom github action to publish with github pages.
- The history chart of a resource counts the changes per day of the last 30 days as stacked bars of the additions, the updates and the deletions, draws the inventory as a line above them and names the time, the unit and the resource it counts in a caption; a resource which answers no statistics, a request which is still asked and a request which failed are told apart from a resource without any change (#601).

### Fixed
- The identify query of the viewer asks every queryable layer with its own GetFeatureInfo request instead of combining the layers of one service into one query: a service may spend the FEATURE_COUNT of a combined request on its first layers and leave the later ones without an answer, which the inspector then showed as a conclusively empty layer; the layers of one service still share one map request (#700).
- A harvesting job which is redelivered while it runs - by a schedule which fires again, by a retry or by a worker restart - no longer downloads a page whose records are already stored; the page is recognised by the request which asked for it and only missing pages are requested from the remote catalogue again (#688).
- A harvesting run which could not fetch all its pages says so: a task which gave up after its retries ends the job as aborted, which the alert of the catalogue, its harvest history and the notification of the background process already answer, instead of leaving the job unfinished until a worker restart re-publishes the whole harvest; a page which the catalogue refused leaves the same trace of missing records as a page which came back short, so the run is answered as one which is not done with instead of a clean completion of a partial snapshot (#690).


### Changed
- moved axis_order_cache package to it's own repo
- Removed pycharm run configurations, cause there are outdated and the common development environment is vscode.
- migrate to docker compose cli plugin v2.x.x

## [0.1.0] - 2023-03-23

Initial versioning starts here. Just to start versioning and track all changes. Some basic features which are extensive tested are described at the added section.

### Added

- This CHANGELOG file to track all changes of this project
- OpenApi Schema for the hole json:api
- [crud](https://de.wikipedia.org/wiki/CRUD) operations for all django models accessable via the [json:api](https://jsonapi.org/) under /api/
- security proxy tested for wms v1.3.0 and wfs v2.0.0
- ows context api available under /mrmap-proxy/ows/


### Removed

- The versioning of the json:api is no longer part of the url. For now we will serve the json:api as it is and changes will be described in this document.
- Moves the react frontend to it's own [repo](https://github.com/mrmap-community/mrmap-react-frontend)