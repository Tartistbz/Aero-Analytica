"""RepoPilot engineering-evaluation workspace for the Streamlit application."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import streamlit as st

from src.ai.providers import ProviderConfig
from src.repopilot.service import (
    CliInvocation,
    RepoPilotServiceError,
    discover_suites,
    discover_tasks,
    load_eval_artifacts,
    pi_environment,
    replay_run,
    run_evaluation,
    runtime_status,
)


RUNTIME_LABELS = {
    "fake": "确定性 Fake",
    "pi": "Pi Agent",
}
STRATEGY_LABELS = {
    "map-only": "仅仓库地图",
    "focused": "聚焦文件",
    "focused+history": "聚焦文件 + 历史压缩",
}
RESULT_KEY = "repopilot_last_evaluation"


def render_repopilot_workspace(active_provider: Optional[ProviderConfig]) -> None:
    """Render controls and read-only evidence for a RepoPilot evaluation."""

    status = runtime_status()
    if not all(status.values()):
        missing = []
        if not status["node"]:
            missing.append("Node.js")
        if not status["npm"]:
            missing.append("npm")
        if not status["dependencies"]:
            missing.append("node_modules")
        if not status["cli"]:
            missing.append("RepoPilot CLI")
        st.error(f"工程评测不可用：缺少 {', '.join(missing)}")
        return

    tasks = discover_tasks()
    suites = discover_suites()
    if not tasks or not suites:
        st.error("未发现评测任务或任务集。")
        return

    st.subheader("工程评测")
    st.caption("内置任务：PX4 / ArduPilot / ROS 确定性 fixtures")

    source_col, runtime_col, strategy_col = st.columns([1.2, 1, 1.4])
    with source_col:
        source_kind = st.radio(
            "执行范围",
            ["任务集", "单个任务"],
            horizontal=True,
            key="repopilot_source_kind",
        )
    with runtime_col:
        runtime = st.selectbox(
            "运行时",
            list(RUNTIME_LABELS),
            format_func=RUNTIME_LABELS.get,
            key="repopilot_runtime",
        )
    with strategy_col:
        strategy = st.selectbox(
            "上下文策略",
            list(STRATEGY_LABELS),
            format_func=STRATEGY_LABELS.get,
            key="repopilot_strategy",
        )

    selected_suite = None
    selected_task = None
    if source_kind == "任务集":
        selected_suite = st.selectbox(
            "任务集",
            suites,
            format_func=lambda item: item.label,
            key="repopilot_suite",
        )
    else:
        selected_task = st.selectbox(
            "任务",
            tasks,
            format_func=lambda item: item.label,
            key="repopilot_task",
        )
        if selected_task.prompt:
            st.caption(selected_task.prompt)

    if runtime == "pi":
        if active_provider is None:
            st.warning("Pi Agent 运行需要先在侧边栏选择 API Provider。")
        else:
            st.caption(f"Pi 使用当前 Provider：{active_provider.name} · {active_provider.model}")

    if st.button(
        "开始评测",
        icon=":material/play_arrow:",
        type="primary",
        key="repopilot_start",
    ):
        try:
            process_env = pi_environment(active_provider) if runtime == "pi" and active_provider else None
            if runtime == "pi" and process_env is None:
                raise RepoPilotServiceError("请先在侧边栏配置并选择 AI Provider。")
            with st.spinner("RepoPilot 正在隔离执行并验证任务..."):
                invocation = run_evaluation(
                    suite=selected_suite.path if selected_suite else None,
                    task=selected_task.path if selected_task else None,
                    runtime=runtime,
                    strategy=strategy,
                    pi_env=process_env,
                )
        except RepoPilotServiceError as exc:
            st.error(str(exc))
        else:
            st.session_state[RESULT_KEY] = invocation
            if invocation.payload is None:
                st.error(invocation.error or "评测未返回结果。")
            else:
                st.rerun()

    invocation = st.session_state.get(RESULT_KEY)
    if isinstance(invocation, CliInvocation) and invocation.payload:
        _render_evaluation_result(invocation)


def _render_evaluation_result(invocation: CliInvocation) -> None:
    payload = invocation.payload or {}
    artifacts = load_eval_artifacts(payload)
    total = int(payload.get("total", len(artifacts)) or 0)
    succeeded = int(payload.get("succeeded", 0) or 0)
    success_rate = float(payload.get("successRate", 0) or 0)
    tool_calls = sum(item.get("metrics", {}).get("tool_calls", 0) for item in artifacts)
    duration_ms = sum(item.get("metrics", {}).get("duration_ms", 0) for item in artifacts)
    recovery_count = sum(item.get("metrics", {}).get("recovery_count", 0) for item in artifacts)
    tests_passed = sum(
        1 for item in artifacts if item.get("metrics", {}).get("test_passed")
    )

    st.divider()
    if invocation.error:
        st.warning(invocation.error)
    elif succeeded == total:
        st.success("评测完成，所有任务已通过验证。")
    else:
        st.warning("评测完成，存在未通过验证的任务。")

    metric_columns = st.columns(6)
    metric_columns[0].metric("任务", f"{succeeded}/{total}")
    metric_columns[1].metric("成功率", f"{success_rate * 100:.1f}%")
    metric_columns[2].metric("测试通过", f"{tests_passed}/{total}")
    metric_columns[3].metric("工具调用", tool_calls)
    metric_columns[4].metric("耗时", _duration_label(duration_ms))
    metric_columns[5].metric("恢复", recovery_count)

    report = Path(str(payload.get("report") or ""))
    if report.is_file():
        st.download_button(
            "下载 HTML 报告",
            data=report.read_bytes(),
            file_name=report.name,
            mime="text/html",
            key=f"repopilot_report_{report.name}",
        )

    rows = [
        {
            "任务": artifact.get("task_id"),
            "状态": artifact.get("status"),
            "测试": "通过" if artifact.get("metrics", {}).get("test_passed") else "未通过",
            "工具": artifact.get("metrics", {}).get("tool_calls", 0),
            "上下文 token": artifact.get("metrics", {}).get("context_tokens", 0),
            "文件": artifact.get("metrics", {}).get("selected_files", 0),
            "恢复": artifact.get("metrics", {}).get("recovery_count", 0),
            "耗时 (ms)": artifact.get("metrics", {}).get("duration_ms", 0),
            "失败分类": artifact.get("failure_category") or "-",
        }
        for artifact in artifacts
    ]
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")

    for artifact in artifacts:
        _render_run_details(artifact)


def _render_run_details(artifact: dict[str, Any]) -> None:
    title = f"{artifact.get('task_id', 'unknown')} · {artifact.get('status', 'unknown')}"
    with st.expander(title):
        if artifact.get("unavailable"):
            st.warning("该运行产物已不可用。")
            return

        context = artifact.get("context", {})
        context_columns = st.columns(3)
        context_columns[0].metric("策略", context.get("strategy") or "-")
        context_columns[1].metric(
            "上下文", f"{context.get('estimated_tokens', 0)}/{context.get('budget_tokens', 0)}"
        )
        context_columns[2].metric("选中文件", len(context.get("selected_files", [])))

        selected_files = context.get("selected_files", [])
        if selected_files:
            st.code("\n".join(str(item) for item in selected_files), language="text")

        verification = artifact.get("verification", {})
        checks = verification.get("checks", [])
        if checks:
            st.markdown("##### 验证")
            st.dataframe(
                [
                    {
                        "检查": check["name"],
                        "状态": "通过" if check["ok"] else "未通过",
                        "耗时 (ms)": check["duration_ms"],
                    }
                    for check in checks
                ],
                hide_index=True,
                width="stretch",
            )
            output_checks = [check for check in checks if check["output"]]
            if output_checks:
                output_index = st.selectbox(
                    "检查输出",
                    range(len(output_checks)),
                    format_func=lambda index: output_checks[index]["name"],
                    key=f"repopilot_check_output_{artifact.get('run_id', 'unknown')}",
                )
                st.code(output_checks[output_index]["output"], language="text")

        trace = artifact.get("trace", {})
        st.markdown("##### Trace")
        trace_columns = st.columns(4)
        trace_columns[0].metric("事件", trace.get("event_count", 0))
        trace_columns[1].metric("工具", trace.get("tool_calls", 0))
        trace_columns[2].metric("验证", trace.get("verification_events", 0))
        trace_columns[3].metric("恢复", trace.get("recovery_count", 0))
        timeline = trace.get("timeline", [])
        if timeline:
            st.dataframe(timeline, hide_index=True, width="stretch")

        replay_key = f"repopilot_replay_{artifact.get('run_id', 'unknown')}"
        if st.button("回放 Trace", icon=":material/replay:", key=replay_key):
            try:
                with st.spinner("正在读取 Trace..."):
                    replay = replay_run(Path(str(artifact["run_dir"])))
            except RepoPilotServiceError as exc:
                st.error(str(exc))
            else:
                if replay.payload:
                    st.json(replay.payload)
                else:
                    st.error(replay.error or "Trace 回放失败。")

        st.markdown("##### 最终 Diff")
        diff = artifact.get("diff") or "(无变更)"
        st.code(diff, language="diff")


def _duration_label(duration_ms: int) -> str:
    if duration_ms < 1_000:
        return f"{duration_ms} ms"
    return f"{duration_ms / 1_000:.1f} s"
