# src/ui/charts.py
import plotly.graph_objects as go
import streamlit as st


def get_plot_columns(df):
    """Return drawable data columns in their DataFrame order."""
    return [column for column in df.columns if column not in ["timestamp", "mode"]]


def resolve_visible_columns(df, visible_columns=None):
    """Filter requested visibility to drawable columns without changing order."""
    plot_columns = get_plot_columns(df)
    if visible_columns is None:
        return plot_columns
    visible = set(visible_columns)
    return [column for column in plot_columns if column in visible]


def render_main_chart(df, visible_columns=None):
    """渲染带模式背景的专业双轴图表"""
    if df.empty:
        st.info("👈 请在下方选择字段或在右侧向 AI 提问以生成图表")
        return

    fig = go.Figure()
    
    # 1. 绘制当前可见的数据线（跳过时间戳和模式列）
    available_plot_cols = get_plot_columns(df)
    if not available_plot_cols:
        st.info("所选字段在当前日志中没有可绘制数据")
        return

    plot_cols = resolve_visible_columns(df, visible_columns)
    if not plot_cols:
        st.info("当前已隐藏所有曲线")
        return

    for col_name in plot_cols:
        # 智能双轴：状态/计数类放右轴
        is_sec = any(x in col_name for x in ["Status", "Mode", "NSats", "Health", "Id", "Num"])
        
        fig.add_trace(go.Scatter(
            x=df["timestamp"], 
            y=df[col_name], 
            name=col_name,
            yaxis="y2" if is_sec else "y1",
            mode='lines',
            line=dict(width=1.5),
            hovertemplate='%{y:.2f} (s: %{x})'
        ))

    # 2. 模式背景渲染
    if 'mode' in df.columns:
        # 简单处理模式切换点
        mode_series = df['mode'].fillna("UNKNOWN")
        change_indices = df.index[mode_series != mode_series.shift()].tolist()
        for i in range(len(change_indices)):
            start_idx = change_indices[i]
            end_idx = change_indices[i+1] if i+1 < len(change_indices) else df.index[-1]
            
            start_t = df.loc[start_idx, 'timestamp']
            end_t = df.loc[end_idx, 'timestamp']
            mode_name = df.loc[start_idx, 'mode']
            
            fig.add_vrect(
                x0=start_t, x1=end_t,
                fillcolor="gray", opacity=0.08,
                layer="below", line_width=0,
                annotation_text=str(mode_name), 
                annotation_position="top left",
                annotation_font=dict(size=10, color="gray")
            )

    fig.update_layout(
        height=550,
        hovermode="x unified",
        template="plotly_white",
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            itemclick="toggle",
            itemdoubleclick="toggleothers",
        ),
        xaxis=dict(title="时间 (Seconds)", rangeslider=dict(visible=True)),
        yaxis=dict(title="物理量数值"),
        yaxis2=dict(title="状态/计数", overlaying="y", side="right"),
        margin=dict(l=10, r=10, t=40, b=10)
    )
    
    st.plotly_chart(fig, use_container_width=True)
