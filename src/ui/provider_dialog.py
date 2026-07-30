import json
from typing import Dict, Optional

import streamlit as st

from src.ai.providers import (
    ANTHROPIC_COMPATIBLE,
    OPENAI_COMPATIBLE,
    PROVIDER_TEMPLATES,
    PROTOCOL_LABELS,
    ProviderClient,
    ProviderConfig,
    ProviderConfigError,
    ProviderRequestError,
    ProviderStore,
    create_provider_from_template,
    get_provider_template,
)


def _parse_headers(value: str) -> Dict[str, str]:
    if not value.strip():
        return {}
    try:
        headers = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ProviderConfigError("自定义 Headers 必须是有效 JSON") from exc
    if not isinstance(headers, dict):
        raise ProviderConfigError("自定义 Headers 必须是 JSON 对象")
    return {str(key): str(item) for key, item in headers.items()}


def _headers_text(headers: Dict[str, str]) -> str:
    return json.dumps(headers, ensure_ascii=False, indent=2)


def _build_edited_provider(
    provider: ProviderConfig,
    *,
    name: str,
    protocol: str,
    base_url: str,
    endpoint: str,
    api_key: str,
    model: str,
    models_endpoint: str,
    supports_json_mode: bool,
    headers_text: str,
    require_model: bool = True,
) -> ProviderConfig:
    edited = ProviderConfig(
        id=provider.id,
        name=name,
        template_id=provider.template_id,
        protocol=protocol,
        base_url=base_url,
        endpoint=endpoint,
        api_key=api_key,
        model=model,
        models_endpoint=models_endpoint,
        supports_json_mode=supports_json_mode,
        custom_headers=_parse_headers(headers_text),
        created_at=provider.created_at,
    )
    edited.validate(require_model=require_model)
    return edited


def _test_provider(provider: ProviderConfig) -> None:
    with st.spinner("正在连接 Provider..."):
        result = ProviderClient(provider).test_connection()
    preview = result.strip().replace("\n", " ")[:120]
    st.success(f"连接成功：{preview}")


def _apply_model_selection(model_key: str, selector_key: str) -> None:
    st.session_state[model_key] = st.session_state[selector_key]


def _apply_pending_model(model_key: str) -> None:
    pending_key = f"{model_key}_pending"
    if pending_key in st.session_state:
        st.session_state[model_key] = st.session_state.pop(pending_key)


def _render_model_picker(model_key: str, models_key: str) -> None:
    models = st.session_state.get(models_key, [])
    if not models:
        return

    selector_key = f"{models_key}_selector"
    selected_model = st.session_state.get(model_key, "")
    if st.session_state.get(selector_key) not in models:
        st.session_state[selector_key] = (
            selected_model if selected_model in models else models[0]
        )
    st.selectbox(
        "可用模型",
        models,
        key=selector_key,
        on_change=_apply_model_selection,
        args=(model_key, selector_key),
    )


def _fetch_provider_models(
    provider: ProviderConfig,
    *,
    model_key: str,
    models_key: str,
) -> None:
    with st.spinner("正在获取模型列表..."):
        models = ProviderClient(provider, timeout=20.0).list_models()
    st.session_state[models_key] = models
    st.session_state.pop(f"{models_key}_selector", None)
    if st.session_state.get(model_key) not in models:
        st.session_state[f"{model_key}_pending"] = models[0]
    st.toast(f"已获取 {len(models)} 个模型")
    st.rerun(scope="fragment")


def render_provider_sidebar(store: ProviderStore) -> Optional[ProviderConfig]:
    st.markdown("#### AI Provider")
    try:
        state = store.load()
    except ProviderConfigError as exc:
        st.error(str(exc))
        state = None

    active_provider = None
    if state and state.providers:
        provider_ids = list(state.providers)
        current_id = state.current if state.current in state.providers else provider_ids[0]
        selected_id = st.radio(
            "当前 Provider",
            provider_ids,
            index=provider_ids.index(current_id),
            format_func=lambda provider_id: state.providers[provider_id].name,
            key="active_provider_selector",
            label_visibility="collapsed",
        )
        if selected_id != state.current:
            try:
                state = store.set_current(selected_id)
            except ProviderConfigError as exc:
                st.error(str(exc))
            else:
                st.rerun()
        active_provider = state.providers.get(selected_id)
        if active_provider:
            st.caption(f"{active_provider.protocol_label} · {active_provider.model}")
    else:
        st.info("尚未配置 AI Provider")

    if st.button("配置 API", use_container_width=True, key="open_provider_dialog"):
        render_provider_dialog(store)
    return active_provider


@st.dialog("配置 API Provider", width="large")
def render_provider_dialog(store: ProviderStore) -> None:
    st.caption("配置保存在本机，不会写入 Git；API Key 请按敏感凭据管理。")
    add_tab, manage_tab = st.tabs(["新增 Provider", "管理 Provider"])

    with add_tab:
        _render_add_provider(store)

    with manage_tab:
        _render_manage_provider(store)


def _render_add_provider(store: ProviderStore) -> None:
    template_ids = [template.id for template in PROVIDER_TEMPLATES]
    template_id = st.selectbox(
        "服务商模板",
        template_ids,
        format_func=lambda item: get_provider_template(item).name,
        key="provider_new_template",
    )
    template = get_provider_template(template_id)
    st.caption(PROTOCOL_LABELS[template.protocol])
    model_key = f"provider_new_model_{template.id}"
    models_key = f"provider_new_models_{template.id}"
    _apply_pending_model(model_key)
    if model_key not in st.session_state:
        st.session_state[model_key] = template.model

    name = st.text_input(
        "Provider 名称",
        value=template.name,
        key=f"provider_new_name_{template.id}",
    )
    base_url = st.text_input(
        "Base URL",
        value=template.base_url,
        placeholder="https://api.example.com/v1",
        key=f"provider_new_base_url_{template.id}",
    )

    endpoint_col, model_col = st.columns(2)
    with endpoint_col:
        endpoint = st.text_input(
            "API 端点",
            value=template.endpoint,
            key=f"provider_new_endpoint_{template.id}",
        )
    with model_col:
        model = st.text_input(
            "模型",
            key=model_key,
        )

    api_key = st.text_input(
        "API Key",
        type="password",
        key=f"provider_new_key_{template.id}",
    )
    with st.expander("高级设置"):
        models_endpoint = st.text_input(
            "模型列表端点",
            value=template.models_endpoint,
            placeholder="models 或完整 URL",
            key=f"provider_new_models_endpoint_{template.id}",
        )
        supports_json_mode = st.checkbox(
            "发送 response_format JSON 模式",
            value=template.supports_json_mode,
            key=f"provider_new_json_mode_{template.id}",
        )
        headers_text = st.text_area(
            "自定义 Headers (JSON)",
            value="{}",
            height=120,
            key=f"provider_new_headers_{template.id}",
        )

    fetch_col, test_col, save_col = st.columns(3)
    if fetch_col.button(
        "获取模型",
        icon=":material/refresh:",
        use_container_width=True,
        key=f"provider_fetch_models_{template.id}",
    ):
        try:
            provider = create_provider_from_template(
                template.id,
                name=name,
                base_url=base_url,
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                models_endpoint=models_endpoint,
                supports_json_mode=supports_json_mode,
                custom_headers=_parse_headers(headers_text),
                require_model=False,
            )
            _fetch_provider_models(
                provider,
                model_key=model_key,
                models_key=models_key,
            )
        except (ProviderConfigError, ProviderRequestError) as exc:
            st.error(str(exc))

    if test_col.button("测试连接", use_container_width=True, key=f"provider_test_{template.id}"):
        try:
            provider = create_provider_from_template(
                template.id,
                name=name,
                base_url=base_url,
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                models_endpoint=models_endpoint,
                supports_json_mode=supports_json_mode,
                custom_headers=_parse_headers(headers_text),
            )
            _test_provider(provider)
        except (ProviderConfigError, ProviderRequestError) as exc:
            st.error(str(exc))

    if save_col.button(
        "保存并启用",
        type="primary",
        use_container_width=True,
        key=f"provider_save_{template.id}",
    ):
        try:
            provider = create_provider_from_template(
                template.id,
                name=name,
                base_url=base_url,
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                models_endpoint=models_endpoint,
                supports_json_mode=supports_json_mode,
                custom_headers=_parse_headers(headers_text),
            )
            store.upsert(provider)
            store.set_current(provider.id)
        except ProviderConfigError as exc:
            st.error(str(exc))
        else:
            st.session_state.pop("active_provider_selector", None)
            st.rerun()

    _render_model_picker(model_key, models_key)


def _render_manage_provider(store: ProviderStore) -> None:
    try:
        state = store.load()
    except ProviderConfigError as exc:
        st.error(str(exc))
        return
    if not state.providers:
        st.info("暂无可管理的 Provider")
        return

    provider_ids = list(state.providers)
    selected_id = st.selectbox(
        "选择 Provider",
        provider_ids,
        format_func=lambda provider_id: state.providers[provider_id].name,
        key="provider_manage_selector",
    )
    provider = state.providers[selected_id]
    protocol_options = [OPENAI_COMPATIBLE, ANTHROPIC_COMPATIBLE]
    model_key = f"provider_edit_model_{provider.id}"
    models_key = f"provider_edit_models_{provider.id}"
    _apply_pending_model(model_key)
    if model_key not in st.session_state:
        st.session_state[model_key] = provider.model

    name = st.text_input(
        "Provider 名称",
        value=provider.name,
        key=f"provider_edit_name_{provider.id}",
    )
    protocol = st.selectbox(
        "协议",
        protocol_options,
        index=protocol_options.index(provider.protocol),
        format_func=lambda item: PROTOCOL_LABELS[item],
        key=f"provider_edit_protocol_{provider.id}",
    )
    base_url = st.text_input(
        "Base URL",
        value=provider.base_url,
        key=f"provider_edit_base_url_{provider.id}",
    )

    endpoint_col, model_col = st.columns(2)
    with endpoint_col:
        endpoint = st.text_input(
            "API 端点",
            value=provider.endpoint,
            key=f"provider_edit_endpoint_{provider.id}",
        )
    with model_col:
        model = st.text_input(
            "模型",
            key=model_key,
        )

    api_key = st.text_input(
        "API Key",
        value=provider.api_key,
        type="password",
        key=f"provider_edit_key_{provider.id}",
    )
    st.caption(f"当前密钥：{provider.masked_key}")
    with st.expander("高级设置"):
        models_endpoint = st.text_input(
            "模型列表端点",
            value=provider.models_endpoint,
            placeholder="models 或完整 URL",
            key=f"provider_edit_models_endpoint_{provider.id}",
        )
        supports_json_mode = st.checkbox(
            "发送 response_format JSON 模式",
            value=provider.supports_json_mode,
            key=f"provider_edit_json_mode_{provider.id}",
        )
        headers_text = st.text_area(
            "自定义 Headers (JSON)",
            value=_headers_text(provider.custom_headers),
            height=120,
            key=f"provider_edit_headers_{provider.id}",
        )

    fetch_col, test_col, save_col = st.columns(3)
    if fetch_col.button(
        "获取模型",
        icon=":material/refresh:",
        use_container_width=True,
        key=f"provider_edit_fetch_models_{provider.id}",
    ):
        try:
            edited_provider = _build_edited_provider(
                provider,
                name=name,
                protocol=protocol,
                base_url=base_url,
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                models_endpoint=models_endpoint,
                supports_json_mode=supports_json_mode,
                headers_text=headers_text,
                require_model=False,
            )
            _fetch_provider_models(
                edited_provider,
                model_key=model_key,
                models_key=models_key,
            )
        except (ProviderConfigError, ProviderRequestError) as exc:
            st.error(str(exc))

    if test_col.button("测试连接", use_container_width=True, key=f"provider_edit_test_{provider.id}"):
        try:
            edited_provider = _build_edited_provider(
                provider,
                name=name,
                protocol=protocol,
                base_url=base_url,
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                models_endpoint=models_endpoint,
                supports_json_mode=supports_json_mode,
                headers_text=headers_text,
            )
            _test_provider(edited_provider)
        except (ProviderConfigError, ProviderRequestError) as exc:
            st.error(str(exc))

    if save_col.button(
        "保存修改",
        type="primary",
        use_container_width=True,
        key=f"provider_edit_save_{provider.id}",
    ):
        try:
            edited_provider = _build_edited_provider(
                provider,
                name=name,
                protocol=protocol,
                base_url=base_url,
                endpoint=endpoint,
                api_key=api_key,
                model=model,
                models_endpoint=models_endpoint,
                supports_json_mode=supports_json_mode,
                headers_text=headers_text,
            )
            store.upsert(edited_provider)
        except ProviderConfigError as exc:
            st.error(str(exc))
        else:
            st.session_state.pop("provider_manage_selector", None)
            st.session_state.pop("active_provider_selector", None)
            st.rerun()

    _render_model_picker(model_key, models_key)

    st.divider()
    confirm_delete = st.checkbox(
        f"确认删除 {provider.name}",
        key=f"provider_delete_confirm_{provider.id}",
    )
    if st.button(
        "删除 Provider",
        use_container_width=True,
        disabled=not confirm_delete,
        key=f"provider_delete_{provider.id}",
    ):
        try:
            store.delete(provider.id)
        except ProviderConfigError as exc:
            st.error(str(exc))
        else:
            st.rerun()
