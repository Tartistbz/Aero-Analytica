# app.py
import streamlit as st

# 导入 UI 表现层
from src.ui.styles import apply_custom_styles
from src.ui.components import (
    count_selected_fields,
    render_field_picker_dialog,
    render_selected_fields,
    sanitize_field_mapping,
)
from src.ui.charts import get_plot_columns, render_main_chart
from src.ui.provider_dialog import render_provider_sidebar
from src.ui.repopilot_workspace import render_repopilot_workspace

# 导入逻辑层
from src.analyzer.ardu_parser import ArduPilotParser
from src.analyzer.px4_parser import PX4Parser
from src.log_uploads import store_uploaded_log
from src.ai.agent import AIAgent, AIResponseError
from src.ai.providers import (
    ProviderConfigError,
    ProviderRequestError,
    ProviderStore,
    create_provider_client,
)

# --- 1. 配置与样式 ---
st.set_page_config(layout="wide", page_title="Aero-Analytica | AI 诊断", page_icon="🛸")
apply_custom_styles()  # 调用 styles.py 里的立体样式

# --- 2. 状态管理 ---
if "all_fields" not in st.session_state:
    st.session_state.all_fields = {}
if "target_mapping" not in st.session_state:
    st.session_state.target_mapping = {}
if "selected_mapping" not in st.session_state:
    st.session_state.selected_mapping = {}
if "field_selection_revision" not in st.session_state:
    st.session_state.field_selection_revision = 0
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "parser" not in st.session_state:
    st.session_state.parser = None

provider_store = ProviderStore()

# --- 3. 侧边栏 ---
with st.sidebar:
    st.title("🛸 Aero-Analytica")
    active_provider = render_provider_sidebar(provider_store)
    st.divider()
    uploaded_file = st.file_uploader("📂 上传日志", type=["bin", "ulg"])
    
    if uploaded_file:
        try:
            file_path = store_uploaded_log(
                uploaded_file.name,
                uploaded_file.getbuffer(),
            )
            current_file_path = (
                str(st.session_state.parser.file_path)
                if st.session_state.parser is not None
                else None
            )
            if current_file_path != file_path:
                with st.spinner("🔍 扫描中..."):
                    parser = (
                        ArduPilotParser(file_path)
                        if file_path.lower().endswith(".bin")
                        else PX4Parser(file_path)
                    )
                    all_fields = parser.list_all_fields()
                    st.session_state.parser = parser
                    st.session_state.all_fields = all_fields
                    st.session_state.target_mapping = {}
                    st.session_state.selected_mapping = {}
                    st.session_state.field_selection_revision += 1
                    st.session_state.pop("field_picker_message", None)
                    st.session_state.pop("field_picker_search", None)
                st.success("加载成功")
        except (OSError, ValueError) as exc:
            st.error(f"日志加载失败：{exc}")

# --- 4. 主页面布局 ---
flight_tab, repair_tab = st.tabs(["飞行问题诊断", "代码问题修复"])

with flight_tab:
    col_left, col_right = st.columns([2.2, 1], gap="large")

    # 左侧：可视化与控制
    with col_left:
        st.subheader("📈 数据分析画布")

        if st.session_state.all_fields:
            selected_mapping = sanitize_field_mapping(
                st.session_state.selected_mapping,
                st.session_state.all_fields,
            )

            title_column, add_column, clear_column = st.columns(
                [2.8, 1.15, 0.85], vertical_alignment="center"
            )
            with title_column:
                st.markdown("#### 当前分析字段")
                st.caption(
                    f"{len(selected_mapping)} 个消息 · "
                    f"{count_selected_fields(selected_mapping)} 个字段"
                )
            if add_column.button(
                "添加字段",
                icon=":material/add:",
                width="stretch",
                key="open_field_picker",
            ):
                render_field_picker_dialog(st.session_state.all_fields)
            if clear_column.button(
                "清空",
                icon=":material/delete_sweep:",
                width="stretch",
                disabled=not selected_mapping,
                key="clear_selected_fields",
            ):
                st.session_state.selected_mapping = {}
                st.session_state.field_selection_revision += 1
                st.rerun()

            selected = render_selected_fields(
                st.session_state.all_fields,
                selected_mapping,
                st.session_state.target_mapping,
                st.session_state.field_selection_revision,
            )
            if selected != selected_mapping:
                st.session_state.selected_mapping = selected
                st.session_state.field_selection_revision += 1
                st.rerun()

            st.divider()
            if selected:
                df = st.session_state.parser.get_custom_dataframe(selected)
                plot_columns = get_plot_columns(df)
                visible_columns = None
                if plot_columns:
                    visible_columns = st.pills(
                        "显示曲线",
                        options=plot_columns,
                        selection_mode="multi",
                        default=plot_columns,
                        key=(
                            "visible_chart_series_"
                            f"{st.session_state.field_selection_revision}"
                        ),
                        help="取消标签可隐藏曲线；双击图例可临时只看一条。",
                        width="stretch",
                    )
                render_main_chart(df, visible_columns)
            else:
                st.info("向 AI 提问或添加字段后，图表会显示在这里。")
        else:
            st.info("💡 请先上传无人机日志文件。")

    # 右侧：AI 智能对话
    with col_right:
        st.subheader("💬 AI 智能助手")
        chat_box = st.container(height=650)

        # 渲染历史
        for chat in st.session_state.chat_history:
            with chat_box.chat_message(chat["role"]): st.markdown(chat["content"])

        if prompt := st.chat_input("输入分析指令..."):
            if active_provider is None:
                st.error("请先配置并选择 AI Provider")
            elif st.session_state.parser is None:
                st.error("请先上传无人机日志")
            else:
                st.session_state.chat_history.append({"role": "user", "content": prompt})
                with chat_box.chat_message("user"): st.markdown(prompt)

                # 业务流程
                agent = AIAgent(create_provider_client(active_provider))
                with chat_box.chat_message("assistant"):
                    try:
                        # 1. AI 选字段
                        with st.spinner("🧠 识别字段..."):
                            plan = agent.get_dispatch_plan(
                                prompt, st.session_state.all_fields
                            )
                            plan = sanitize_field_mapping(
                                plan, st.session_state.all_fields
                            )
                            st.session_state.target_mapping = plan
                            st.session_state.selected_mapping = plan
                            st.session_state.field_selection_revision += 1
                        # 2. AI 出报告
                        with st.spinner("📊 诊断中..."):
                            temp_df = st.session_state.parser.get_custom_dataframe(
                                plan
                            )
                            report = agent.get_analysis_report(prompt, temp_df)
                    except (
                        AIResponseError,
                        ProviderConfigError,
                        ProviderRequestError,
                    ) as exc:
                        error_message = f"分析失败：{exc}"
                        st.error(error_message)
                        st.session_state.chat_history.append(
                            {"role": "assistant", "content": error_message}
                        )
                        st.rerun()
                    else:
                        st.markdown(report)
                        st.session_state.chat_history.append(
                            {"role": "assistant", "content": report}
                        )
                        st.rerun()

with repair_tab:
    render_repopilot_workspace(active_provider)
