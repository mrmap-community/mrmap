# MrMap Development

MrMap is maintained as a [GitHub project](https://github.com/mrmap-community/mrmap) under the MIT license. Users are encouraged to submit GitHub issues for feature requests and bug reports, however we are very selective about pull requests. Please see the `CONTRIBUTING` guide for more direction on contributing to MrMap.

## Communication

There are several official forums for communication among the developers and community members:

* [GitHub issues](https://github.com/mrmap-community/mrmap/issues) - All feature requests, bug reports, and other substantial changes to the code base **must** be documented in an issue.
* [GitHub Discussions](https://github.com/mrmap-community/mrmap/discussions) - The preferred forum for general discussion and support issues. Ideal for shaping a feature request prior to submitting an issue.

## Project Structure

All development of the current MrMap release occurs in the `develop` branch; releases are packaged from the `master` branch. The `master` branch should _always_ represent the current stable release in its entirety, such that installing MrMap by either downloading a packaged release or cloning the `master` branch provides the same code base.

MrMap components are arranged into functional subsections called _apps_ (a carryover from Django vernacular). Each app holds the models, views, and templates relevant to a particular function:

* `users`: Customize the Django authentication system
* `structure`: todo
* `service`: todo
* `quality`: todo
* `monitoring`: todo
* `editor`: todo
* `csw`: todo
* `breadcrumb`: todo
* `api`: todo
