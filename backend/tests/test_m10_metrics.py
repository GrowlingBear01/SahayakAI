import unittest

from scripts.measure_m10 import summarize_runs


class M10MetricsTests(unittest.TestCase):
    def test_summary_uses_all_runs_as_denominator_and_median_latency(self) -> None:
        summary = summarize_runs(
            [
                {"passed": True, "latency_seconds": 10.0},
                {"passed": False, "latency_seconds": 30.0},
                {"passed": True, "latency_seconds": 20.0},
            ]
        )

        self.assertEqual(summary["target_runs"], 20)
        self.assertEqual(summary["completed_runs"], 3)
        self.assertEqual(summary["passes"], 2)
        self.assertEqual(summary["failures"], 1)
        self.assertAlmostEqual(summary["pass_rate"], 2 / 3)
        self.assertEqual(summary["median_latency_seconds"], 20.0)

    def test_empty_summary_has_no_fabricated_latency(self) -> None:
        summary = summarize_runs([])

        self.assertEqual(summary["completed_runs"], 0)
        self.assertEqual(summary["pass_rate"], 0)
        self.assertIsNone(summary["median_latency_seconds"])


if __name__ == "__main__":
    unittest.main()
