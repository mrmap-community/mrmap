import importlib.util
import pathlib
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).with_name("sync_project_overview.py")
spec = importlib.util.spec_from_file_location("project_sync", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProjectSyncTests(unittest.TestCase):
    def test_closing_pr_and_branch_mapping(self):
        idx = module.pr_index([
            {"body": "Closes #1249", "headRefName": "feature/abc", "isDraft": False},
            {"body": "", "headRefName": "agent/issue-1328-fix", "isDraft": True},
        ])
        self.assertEqual(len(idx[1249]), 1)
        self.assertEqual(len(idx[1328]), 1)

    def test_phase_is_not_approval(self):
        open_issue = {"number": 1, "state": "OPEN", "labels": [{"name": "agent: approved"}]}
        self.assertEqual(module.issue_phase(open_issue, {}), "Backlog")
        self.assertEqual(module.issue_phase({**open_issue, "labels": [{"name": "agent: paused"}]}, {}), "Blocked")
        self.assertEqual(module.issue_phase(open_issue, {1: [{"isDraft": False}]}), "Review")
        self.assertEqual(module.issue_phase(open_issue, {1: [{"isDraft": True}]}), "In Progress")
        self.assertEqual(module.issue_phase({**open_issue, "state": "CLOSED"}, {}), "Done")

    def test_project_item_fields_extract_custom_values(self):
        item = {"fieldValues": {"nodes": [
            {"__typename": "ProjectV2ItemFieldSingleSelectValue",
             "field": {"name": "Development Phase"}, "name": "In Progress"},
            {"__typename": "ProjectV2ItemFieldSingleSelectValue",
             "field": {"name": "Agent Status"}, "name": "Approved"},
            {"__typename": "ProjectV2ItemFieldTextValue",
             "field": {"name": "Notes"}, "text": "example"},
        ]}}
        self.assertEqual(module.project_item_fields(item), {
            "Development Phase": "In Progress",
            "Agent Status": "Approved",
            "Notes": "example",
        })


if __name__ == "__main__":
    unittest.main()
