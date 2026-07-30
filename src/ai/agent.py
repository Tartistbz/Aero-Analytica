# src/ai/agent.py
import json
from difflib import SequenceMatcher

import numpy as np
from .prompts import DISPATCHER_PROMPT, ANALYST_PROMPT


class AIResponseError(ValueError):
    pass


class AIAgent:
    ANALYSIS_MAX_TOKENS = 4000
    CONTINUATION_MAX_TOKENS = 2500
    MAX_CONTINUATIONS = 2

    def __init__(self, client):
        self.client = client

    def get_dispatch_plan(self, user_query, fields_map):
        """让 AI 决定提取哪些数据"""
        # 将字段字典转为 AI 可读文本
        context = "\n".join([f"- {m}: {', '.join(f)}" for m, f in fields_map.items()])
        
        content = self.client.complete(
            [
                {"role": "system", "content": DISPATCHER_PROMPT.format(fields_context=context)},
                {"role": "user", "content": user_query}
            ],
            json_mode=True,
            max_tokens=1000,
        )
        content = content.strip()
        # 清理 Markdown 标记
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1]).strip()
        try:
            plan = json.loads(content)
        except json.JSONDecodeError as exc:
            raise AIResponseError("AI 未返回有效的字段映射 JSON") from exc
        return self._validate_dispatch_plan(plan, fields_map)

    def get_analysis_report(self, user_query, df):
        """让 AI 给出诊断结论"""
        if df.empty:
            raise AIResponseError("选定字段没有提取到可分析的数据")
        # 统计摘要
        numeric_df = df.select_dtypes(include=[np.number]).drop(columns=['timestamp'], errors='ignore')
        stats_text = (
            numeric_df.describe().to_string()
            if not numeric_df.empty
            else "没有可用数值列"
        )
        
        # 时序采样 (约 15 行)
        sample_data = df.iloc[::max(1, len(df)//15)].to_string(index=False)
        
        messages = [
            {
                "role": "system",
                "content": ANALYST_PROMPT.format(
                    stats_text=stats_text,
                    sample_data=sample_data,
                ),
            },
            {"role": "user", "content": user_query},
        ]
        complete_with_metadata = getattr(
            self.client,
            "complete_with_metadata",
            None,
        )
        if complete_with_metadata is None:
            return self.client.complete(
                messages,
                max_tokens=self.ANALYSIS_MAX_TOKENS,
            )

        result = complete_with_metadata(
            messages,
            max_tokens=self.ANALYSIS_MAX_TOKENS,
        )
        report = result.text
        continuation_count = 0
        while result.truncated and continuation_count < self.MAX_CONTINUATIONS:
            continuation_messages = [
                *messages,
                {"role": "assistant", "content": report},
                {
                    "role": "user",
                    "content": (
                        "上一个回答因输出长度限制被截断。请严格从上面回答"
                        "中断的位置继续，不要重复已有内容。先补全未完成的"
                        "句子，再完成剩余分析和建议。只输出续写正文，"
                        "并确保本次输出以完整句子结束。"
                    ),
                },
            ]
            result = complete_with_metadata(
                continuation_messages,
                max_tokens=self.CONTINUATION_MAX_TOKENS,
            )
            report = self._append_continuation(report, result.text)
            continuation_count += 1

        if result.truncated:
            report = report.rstrip() + (
                "\n\n> 注：报告连续达到模型输出上限，"
                "当前结果可能仍不完整。"
            )
        return report

    @staticmethod
    def _append_continuation(report, continuation):
        existing = report.rstrip()
        addition = continuation.lstrip()
        if not addition:
            return existing

        max_overlap = min(500, len(existing), len(addition))
        for overlap_size in range(max_overlap, 7, -1):
            if existing.endswith(addition[:overlap_size]):
                addition = addition[overlap_size:].lstrip()
                break
        if not addition:
            return existing

        sentence_endings = ("。", "！", "？", "!", "?", "\n", "```")
        separator = "\n\n" if existing.endswith(sentence_endings) else ""
        return f"{existing}{separator}{addition}"

    @staticmethod
    def _resolve_name(requested_name, available_names, *, allow_fuzzy=False):
        if not isinstance(requested_name, str):
            return None

        available = [name for name in available_names if isinstance(name, str)]
        if requested_name in available:
            return requested_name

        casefold_matches = [
            name for name in available if name.casefold() == requested_name.casefold()
        ]
        if len(casefold_matches) == 1:
            return casefold_matches[0]
        if not allow_fuzzy:
            return None

        scored = sorted(
            (
                SequenceMatcher(
                    None,
                    requested_name.casefold(),
                    name.casefold(),
                    autojunk=False,
                ).ratio(),
                name,
            )
            for name in available
        )
        if not scored:
            return None

        best_score, best_name = scored[-1]
        second_score = scored[-2][0] if len(scored) > 1 else 0.0
        if best_score >= 0.84 and best_score - second_score >= 0.08:
            return best_name
        return None

    @classmethod
    def _validate_dispatch_plan(cls, plan, fields_map):
        if not isinstance(plan, dict) or not plan:
            raise AIResponseError("AI 返回的字段映射为空或结构错误")

        validated = {}
        for requested_message, field_names in plan.items():
            message_name = cls._resolve_name(requested_message, fields_map.keys())
            if message_name is None:
                continue
            if not isinstance(field_names, list) or not field_names:
                continue

            resolved_fields = []
            seen_fields = set()
            for requested_field in field_names:
                field_name = cls._resolve_name(
                    requested_field,
                    fields_map[message_name],
                    allow_fuzzy=True,
                )
                if field_name is not None and field_name not in seen_fields:
                    resolved_fields.append(field_name)
                    seen_fields.add(field_name)

            if resolved_fields:
                existing_fields = validated.setdefault(message_name, [])
                existing_fields.extend(
                    field for field in resolved_fields if field not in existing_fields
                )

        if not validated:
            raise AIResponseError("AI 返回的字段映射中没有可用的消息或字段")
        return validated
