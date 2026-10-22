# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.x.x] - UNRELEASED

### Added
- Cross-service attention list, app-bar count and dashboard card for service failures, update reviews and overdue schedules (#567).
- Work queue card on the dashboard which counts the alerts, the update reviews and the running and failed background work of everything the user may see, and links to the list of those very records (#601).

### Changed
- building docs with readthedocs.org instead of using custom github action to publish with github pages.
- The history chart of a resource counts the changes per day of the last 30 days as stacked bars of the additions, the updates and the deletions, draws the inventory as a line above them and names the time, the unit and the resource it counts in a caption; a resource which answers no statistics, a request which is still asked and a request which failed are told apart from a resource without any change (#601).


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