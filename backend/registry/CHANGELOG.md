# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2021-12-03
### Added
* This CHANGELOG file to hopefully serve as an evolving example of a
  standardized open source project CHANGELOG.
* Added `swagger-ui` docker container instead of providing it with the backend directly

### Changed
* Renamed `users` app to `accounts` app.
* `Organization` is based on django's `Group` model to add object permissions directly on it.
* Renamed `CommonInfo.owned_by_org` to `CommonInfo.owner` and changed the related destination 
  model to `Group`. 


### Removed
* Removed `jobs` app.
* Removed `swagger-ui` support directrly by the backend.
* Removed all django views.
