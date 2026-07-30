import streamlit as st

def apply_custom_styles():
    st.markdown("""
        <style>
        .stApp { background-color: #f8f9fa; }
        /* 立体卡片 */
        .stExpander {
            background-color: white !important;
            border: 1px solid #e0e0e0 !important;
            border-radius: 12px !important;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
            margin-bottom: 0.8rem !important;
        }
        /* 科技橙渐变按钮 */
        div.stButton > button {
            background: linear-gradient(to bottom, #ff7e5f, #feb47b) !important;
            color: white !important;
            border: none !important;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
        }
        /* 航电蓝标签 */
        span[data-baseweb="tag"] {
            background-color: #2c3e50 !important;
            border-radius: 4px !important;
        }
        </style>
    """, unsafe_allow_html=True)