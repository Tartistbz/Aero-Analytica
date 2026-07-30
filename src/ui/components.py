from collections.abc import Mapping, Sequence

import streamlit as st


def sanitize_field_mapping(mapping, all_fields):
    """Return a deduplicated mapping containing only fields in the active log."""
    if not isinstance(mapping, Mapping) or not isinstance(all_fields, Mapping):
        return {}

    sanitized = {}
    for message, requested_fields in mapping.items():
        if message not in all_fields or isinstance(requested_fields, (str, bytes)):
            continue
        if not isinstance(requested_fields, Sequence):
            continue

        available_fields = set(all_fields[message])
        valid_fields = []
        seen = set()
        for field in requested_fields:
            if field in available_fields and field not in seen:
                valid_fields.append(field)
                seen.add(field)
        if valid_fields:
            sanitized[message] = valid_fields
    return sanitized


def set_message_fields(mapping, message, fields, all_fields):
    """Replace one message selection without changing the other messages."""
    updated = sanitize_field_mapping(mapping, all_fields)
    selected_message = sanitize_field_mapping({message: fields}, all_fields)
    if message in selected_message:
        updated[message] = selected_message[message]
    else:
        updated.pop(message, None)
    return updated


def remove_selected_field(mapping, message, field):
    """Remove one field and drop the message when no fields remain."""
    updated = {
        name: list(fields)
        for name, fields in mapping.items()
        if isinstance(fields, Sequence) and not isinstance(fields, (str, bytes))
    }
    if message not in updated:
        return updated

    updated[message] = [item for item in updated[message] if item != field]
    if not updated[message]:
        updated.pop(message)
    return updated


def filter_field_messages(all_fields, query):
    """Filter message names case-insensitively by message or field name."""
    needle = query.strip().casefold()
    matches = []
    for message, fields in all_fields.items():
        searchable_fields = fields if isinstance(fields, Sequence) else []
        if not needle or needle in str(message).casefold() or any(
            needle in str(field).casefold() for field in searchable_fields
        ):
            matches.append(message)
    return sorted(matches, key=lambda item: str(item).casefold())


def count_selected_fields(mapping):
    return sum(len(fields) for fields in mapping.values())


def render_selected_fields(all_fields, selected_mapping, target_mapping, revision):
    """Render only the active fields and allow fields to be removed in place."""
    current = sanitize_field_mapping(selected_mapping, all_fields)
    if not current:
        st.info("尚未选择分析字段")
        return {}

    rendered = {}
    for message, fields in current.items():
        ai_fields = set(target_mapping.get(message, []))
        label = f"✨ {message}" if ai_fields.intersection(fields) else str(message)
        picked = st.multiselect(
            label,
            options=fields,
            default=fields,
            key=f"selected_fields_{revision}_{message}",
            placeholder="移除后可从字段库重新添加",
        )
        if picked:
            rendered[message] = picked
    return rendered


def _save_dialog_selection(all_fields, message, fields):
    current = st.session_state.get("selected_mapping", {})
    updated = set_message_fields(current, message, fields, all_fields)
    if updated == current:
        return False
    st.session_state.selected_mapping = updated
    st.session_state.field_selection_revision = (
        st.session_state.get("field_selection_revision", 0) + 1
    )
    return True


@st.dialog("添加字段", width="large")
def render_field_picker_dialog(all_fields):
    """Edit the current mapping without rendering widgets for the full field tree."""
    current = sanitize_field_mapping(
        st.session_state.get("selected_mapping", {}), all_fields
    )
    selected_count = count_selected_fields(current)
    st.caption(f"当前已选择 {len(current)} 个消息、{selected_count} 个字段")

    search_query = st.text_input(
        "搜索消息或字段",
        key="field_picker_search",
        placeholder="例如 GPS、Roll、battery",
        icon=":material/search:",
    )
    visible_messages = filter_field_messages(all_fields, search_query)

    if not visible_messages:
        st.warning("没有匹配的消息或字段")
        if st.button("完成", type="primary", width="stretch"):
            st.rerun()
        return

    message = st.selectbox(
        "消息",
        visible_messages,
        format_func=lambda item: f"{item}  ·  {len(all_fields[item])} 个字段",
        key="field_picker_message",
    )
    revision = st.session_state.get("field_selection_revision", 0)
    picked = st.multiselect(
        "字段",
        options=all_fields[message],
        default=current.get(message, []),
        key=f"field_picker_fields_{revision}_{message}",
        placeholder="选择需要绘图和分析的字段",
    )

    apply_column, done_column = st.columns(2)
    if apply_column.button(
        "应用",
        icon=":material/check:",
        width="stretch",
    ):
        changed = _save_dialog_selection(all_fields, message, picked)
        st.toast("字段选择已更新" if changed else "字段选择没有变化")
        if changed:
            st.rerun(scope="fragment")

    if done_column.button(
        "完成",
        type="primary",
        icon=":material/done_all:",
        width="stretch",
    ):
        _save_dialog_selection(all_fields, message, picked)
        st.rerun()
