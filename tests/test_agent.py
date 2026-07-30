import unittest

import pandas as pd

from src.ai.agent import AIAgent, AIResponseError
from src.ai.providers import CompletionResult


class FakeProviderClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return self.responses.pop(0)

    def complete_with_metadata(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, CompletionResult):
            return response
        return CompletionResult(text=response, stop_reason="stop")


class AIAgentTests(unittest.TestCase):
    def test_dispatch_and_analysis_use_common_client(self):
        client = FakeProviderClient(['{"ATT":["Roll","Pitch"]}', "report"])
        agent = AIAgent(client)
        fields = {"ATT": ["Roll", "Pitch", "Yaw"]}

        plan = agent.get_dispatch_plan("分析姿态", fields)
        report = agent.get_analysis_report(
            "分析姿态",
            pd.DataFrame(
                {
                    "timestamp": [0.0, 1.0],
                    "ATT_Roll": [1.0, 2.0],
                    "ATT_Pitch": [0.5, 0.7],
                }
            ),
        )

        self.assertEqual(plan, {"ATT": ["Roll", "Pitch"]})
        self.assertEqual(report, "report")
        self.assertTrue(client.calls[0]["json_mode"])
        self.assertEqual(client.calls[1]["max_tokens"], 4000)
        self.assertEqual(len(client.calls), 2)

    def test_truncated_analysis_is_continued_and_joined(self):
        client = FakeProviderClient(
            [
                CompletionResult("高度源对比：CTUN_Alt（", "length"),
                CompletionResult("估计高度）与气压高度一致。", "stop"),
            ]
        )

        report = AIAgent(client).get_analysis_report(
            "检查高度",
            pd.DataFrame(
                {
                    "timestamp": [0.0, 1.0],
                    "CTUN_Alt": [10.0, 10.2],
                }
            ),
        )

        self.assertEqual(report, "高度源对比：CTUN_Alt（估计高度）与气压高度一致。")
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(client.calls[0]["max_tokens"], 4000)
        self.assertEqual(client.calls[1]["max_tokens"], 2500)
        self.assertEqual(
            [message["role"] for message in client.calls[1]["messages"]],
            ["system", "user", "assistant", "user"],
        )
        self.assertIn("不要重复", client.calls[1]["messages"][-1]["content"])

    def test_unique_field_typo_is_corrected(self):
        agent = AIAgent(FakeProviderClient(['{"MOTB":["ThOut"]}']))

        plan = agent.get_dispatch_plan(
            "飞机动力不足",
            {
                "MOTB": [
                    "LiftMax",
                    "BatVolt",
                    "ThLimit",
                    "ThrAvMx",
                    "ThrOut",
                ]
            },
        )

        self.assertEqual(plan, {"MOTB": ["ThrOut"]})

    def test_invalid_items_are_filtered_when_valid_fields_remain(self):
        agent = AIAgent(
            FakeProviderClient(
                ['{"ATT":["Roll","Missing"],"UNKNOWN":["Value"]}']
            )
        )

        plan = agent.get_dispatch_plan(
            "分析姿态",
            {"ATT": ["Roll", "Pitch"]},
        )

        self.assertEqual(plan, {"ATT": ["Roll"]})

    def test_ambiguous_field_typo_is_not_guessed(self):
        self.assertIsNone(
            AIAgent._resolve_name(
                "Des",
                ["RDes", "PDes"],
                allow_fuzzy=True,
            )
        )

    def test_fully_invalid_dispatch_plan_is_rejected(self):
        agent = AIAgent(FakeProviderClient(['{"ATT":["Missing"]}']))
        with self.assertRaisesRegex(AIResponseError, "没有可用"):
            agent.get_dispatch_plan("分析姿态", {"ATT": ["Roll"]})

    def test_empty_dataframe_is_rejected(self):
        agent = AIAgent(FakeProviderClient([]))
        with self.assertRaisesRegex(AIResponseError, "没有提取到"):
            agent.get_analysis_report("分析姿态", pd.DataFrame())


if __name__ == "__main__":
    unittest.main()
