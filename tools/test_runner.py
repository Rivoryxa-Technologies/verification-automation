import hashlib
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

import run


JOB = {"overall_key": "ok", "cases_key": "cases", "case_key": "outcome_ok",
       "case_identity": "name", "expected_cases": ["complete-case"],
       "required_sources": ["design.sv"]}


class InfrastructureFailureTests(unittest.TestCase):
    def fixture(self, directory):
        checkout = Path(directory) / "checkout"
        checkout.mkdir()
        source = checkout / "design.sv"
        source.write_text("module design; endmodule\n")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        summary = Path(directory) / "summary.json"
        summary.write_text(json.dumps({"schema_version": 1, "ok": True,
                                       "cases": [{"name": "complete-case", "outcome_ok": True}],
                                       "source_sha256": {"design.sv": digest}}))
        return checkout, summary

    def test_valid_fixture_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            self.assertTrue(run.validate_summary(summary, checkout, JOB, 0)[0])

    def test_missing_executable_is_recorded_and_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run.execute(["definitely-not-an-executable-rivoryxa"], Path(directory), 1,
                                 Path(directory) / "exec.log")
            self.assertEqual(result["returncode"], 127)
            self.assertFalse(result["timed_out"])
            self.assertIn("AUTOMATION_EXEC_ERROR", (Path(directory) / "exec.log").read_text())

    def test_timeout_kills_process_and_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run.execute([sys.executable, "-c", "import time; print('began', flush=True); time.sleep(2)"],
                                 Path(directory), 0.05, Path(directory) / "timeout.log")
            self.assertEqual(result["returncode"], 124)
            self.assertTrue(result["timed_out"])
            self.assertIn("AUTOMATION_TIMEOUT", (Path(directory) / "timeout.log").read_text())

    def test_malformed_summary_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            summary.write_text("{broken")
            self.assertEqual(run.validate_summary(summary, checkout, JOB, 0)[1], "summary is malformed")

    def test_json_list_root_fails_without_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            summary.write_text("[]")
            self.assertEqual(run.validate_summary(summary, checkout, JOB, 0)[1],
                             "summary root is not an object")

    def test_json_null_root_fails_without_exception(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            summary.write_text("null")
            self.assertEqual(run.validate_summary(summary, checkout, JOB, 0)[1],
                             "summary root is not an object")

    def test_multiple_summaries_are_ambiguous(self):
        paths = [Path("first.json"), Path("second.json")]
        selected, error = run.select_single_summary(paths)
        self.assertIsNone(selected)
        self.assertEqual(error, "expected exactly one fresh summary; found 2")

    def test_stale_summary_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            not_before = time.time() + 60
            self.assertEqual(run.validate_summary(summary, checkout, JOB, not_before)[1], "summary is stale")

    def test_mismatched_source_hash_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            (checkout / "design.sv").write_text("module changed; endmodule\n")
            self.assertIn("source hash mismatch", run.validate_summary(summary, checkout, JOB, 0)[1])

    def test_truthy_non_boolean_result_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            data = json.loads(summary.read_text())
            data["cases"][0]["outcome_ok"] = 1
            summary.write_text(json.dumps(data))
            self.assertIn("exact case outcomes", run.validate_summary(summary, checkout, JOB, 0)[1])

    def test_extra_failed_case_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            data = json.loads(summary.read_text())
            data["cases"].append({"outcome_ok": False})
            summary.write_text(json.dumps(data))
            self.assertIn("exact case outcomes", run.validate_summary(summary, checkout, JOB, 0)[1])

    def test_truncated_case_matrix_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            data = json.loads(summary.read_text())
            data["cases"] = []
            summary.write_text(json.dumps(data))
            self.assertIn("overall or case", run.validate_summary(summary, checkout, JOB, 0)[1])

    def test_duplicate_case_matrix_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            data = json.loads(summary.read_text())
            data["cases"].append(dict(data["cases"][0]))
            summary.write_text(json.dumps(data))
            self.assertIn("case matrix", run.validate_summary(summary, checkout, JOB, 0)[1])

    def test_omitted_required_source_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            checkout, summary = self.fixture(directory)
            data = json.loads(summary.read_text())
            data["source_sha256"] = {"some-other-file.sv": "0" * 64}
            summary.write_text(json.dumps(data))
            self.assertIn("required source", run.validate_summary(summary, checkout, JOB, 0)[1])


if __name__ == "__main__":
    unittest.main()
