---
name: 🐛 Bug Report
about: Report a reproducible bug in the current release of MrMap
labels: ["type: bug"]
body:
  - type: markdown
    attributes:
      value: "**NOTE:** This form is only for reporting _reproducible bugs_ in a
      current MrMap installation. If you're having trouble with installation or just
      looking for assistance with using MrMap, please visit our
      [discussion forum](https://github.com/mrmap-community/mrmap/discussions) instead."
  - type: input
    attributes:
      label: MrMap version
      description: "What version of MrMap are you currently running?"
      placeholder: v1.0.0
    validations:
      required: true
  - type: dropdown
    attributes:
      label: Python version
      description: "What version of Python are you currently running?"
      options:
        - 3.6
        - 3.7
        - 3.8
        - 3.9
    validations:
      required: true
  - type: textarea
    attributes:
      label: Steps to Reproduce
      description: "Describe in detail the exact steps that someone else can take to
      reproduce this bug using the current stable release of MrMap. Begin with the
      creation of any necessary database objects and call out every operation being
      performed explicitly. If reporting a bug in the REST API, be sure to reconstruct
      the raw HTTP request(s) being made: Don't rely on a client  library such as
      pynetbox."
      placeholder: |
        1. Click on "create widget"
        2. Set foo to 12 and bar to G
        3. Click the "create" button
    validations:
      required: true
  - type: textarea
    attributes:
      label: Expected Behavior
      description: "What did you expect to happen?"
      placeholder: "A new widget should have been created with the specified attributes"
    validations:
      required: true
  - type: textarea
    attributes:
      label: Observed Behavior
      description: "What happened instead?"
      placeholder: "A TypeError exception was raised"
    validations:
      required: true
  - type: markdown
    attributes:
      value: |
        ### Additional information
        You can use the space below to provide any additional information or to attach files.
