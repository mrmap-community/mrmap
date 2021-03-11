---
name: 🐛 Bug report
about: Create a report to help us improve
labels: 'type: bug'
body:
  - type: markdown
    attributes:
      value: "**Note:** This form is only for reporting _reproducible bugs_ in a current MrMap installation. If you're having trouble with installation or just looking for assistance with using MrMap, please visit our [discussion forum](https://github.com/mrmap-community/mrmap/discussions) instead."
  - type: input
    attributes:
      label: MrMap version
      description: "What version of MrMap are you currently running?"
      placeholder: v.1.0.0
    validations:
      required: true
  - type: markdown
    attributes:
      value : |
        ### Additional information
        You can use the space below to provide any additional information or to attach files.
---
