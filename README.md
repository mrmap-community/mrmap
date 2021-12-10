[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=mrmap-community_mrmap&metric=coverage)](https://sonarcloud.io/dashboard?id=mrmap-community_mrmap)
[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=mrmap-community_mrmap&metric=alert_status)](https://sonarcloud.io/dashboard?id=mrmap-community_mrmap)
[![build docs](https://github.com/mrmap-community/mrmap/actions/workflows/publish_docs.yml/badge.svg)](https://mrmap-community.github.io/mrmap/)

<img src="https://github.com/mrmap-community/mrmap/blob/master/mrmap/MrMap/static/images/mr_map.png" width="200">

Mr. Map is a generic registry for geospatial data, metadata, services and their describing documents (e.g. web map services [WMS](https://www.opengeospatial.org/standards/wms), web feature services [WFS](https://www.opengeospatial.org/standards/wfs) and all the other [OGC](http://www.opengeospatial.org/) stuff. A similar project maybe [Hypermap-Registry](http://cga-harvard.github.io/Hypermap-Registry/) - but it lacks off many things which are needed in practice. The information model was inspired by the old well known [mapbender2](https://github.com/mrmap-community/Mapbender2.8) project and somewhen will be replaced by mrmap.

Since most GIS solutions out there are specified on a specific use case or aged without proper support, the need for an free and open source, generic geospatial registry system is high.

MrMap runs as a web application atop the [Django](https://www.djangoproject.com/)
Python framework with a [PostgreSQL](https://www.postgresql.org/) database. For a
complete list of requirements, see `requirements.txt`. The code is available [on GitHub](https://github.com/mrmap-community/mrmap).


### Screenshots

<img src="https://github.com/mrmap-community/mrmap/blob/master/docs/source/images/mrmap_loginpage.png">

### Documentation

The complete documentation for MrMap can be found at [github page](https://mrmap-community.github.io/mrmap/develop/). 

### Discussion

* [GitHub Discussions](https://github.com/mrmap-community/mrmap/discussions) - Discussion forum hosted by GitHub; ideal for Q&A and other structured discussions


## Installation

Please see [the documentation](https://mrmap-community.github.io/mrmap/) for
instructions on installing MrMap.

## Providing Feedback

The best platform for general feedback, assistance, and other discussion is our
[GitHub discussions](https://github.com/mrmap-community/mrmap/discussions).
To report a bug or request a specific feature, please open a GitHub issue using
the [appropriate template](https://github.com/mrmap-community/mrmap/issues/new/choose).

If you are interested in contributing to the development of NetBox, please read
our [contributing guide](CONTRIBUTING.md) prior to beginning any work.
