"""
Mind Map Creator & Editor
-------------------------
An interactive Streamlit app for building, editing, saving, and loading mind maps.

Run with:
    streamlit run app.py
"""

import json
import uuid
from io import BytesIO

import streamlit as st
from streamlit_agraph import agraph, Node, Edge, Config

st.set_page_config(page_title="Mind Map Creator", layout="wide")

# ----------------------------------------------------------------------
# Session state setup
# ----------------------------------------------------------------------
if "nodes" not in st.session_state:
    root_id = str(uuid.uuid4())
    st.session_state.nodes = {
        root_id: {"label": "Central Idea", "color": "#FF6B6B", "size": 30}
    }
    st.session_state.edges = []
    st.session_state.root_id = root_id

if "root_id" not in st.session_state:
    # fallback if nodes exist but root got lost
    st.session_state.root_id = next(iter(st.session_state.nodes))


def add_node(label: str, parent_id: str, color: str = "#4D96FF", size: int = 20):
    new_id = str(uuid.uuid4())
    st.session_state.nodes[new_id] = {"label": label, "color": color, "size": size}
    if parent_id:
        st.session_state.edges.append({"source": parent_id, "target": new_id})
    return new_id


def delete_node(node_id: str):
    if node_id == st.session_state.root_id:
        st.warning("Can't delete the central/root node.")
        return
    # collect descendants to cascade-delete
    to_delete = {node_id}
    changed = True
    while changed:
        changed = False
        for e in st.session_state.edges:
            if e["source"] in to_delete and e["target"] not in to_delete:
                to_delete.add(e["target"])
                changed = True
    st.session_state.nodes = {
        nid: n for nid, n in st.session_state.nodes.items() if nid not in to_delete
    }
    st.session_state.edges = [
        e for e in st.session_state.edges
        if e["source"] not in to_delete and e["target"] not in to_delete
    ]


def rename_node(node_id: str, new_label: str):
    if node_id in st.session_state.nodes:
        st.session_state.nodes[node_id]["label"] = new_label


def export_json() -> str:
    data = {
        "root_id": st.session_state.root_id,
        "nodes": st.session_state.nodes,
        "edges": st.session_state.edges,
    }
    return json.dumps(data, indent=2)


def load_json(data: dict):
    st.session_state.nodes = data["nodes"]
    st.session_state.edges = data["edges"]
    st.session_state.root_id = data["root_id"]


# ----------------------------------------------------------------------
# Sidebar controls
# ----------------------------------------------------------------------
st.sidebar.title("🧠 Mind Map Controls")

id_to_label = {nid: n["label"] for nid, n in st.session_state.nodes.items()}

with st.sidebar.expander("➕ Add Node", expanded=True):
    new_label = st.text_input("Node label", key="add_label")
    parent_choice = st.selectbox(
        "Parent node",
        options=list(id_to_label.keys()),
        format_func=lambda x: id_to_label[x],
        key="add_parent",
    )
    node_color = st.color_picker("Node color", "#4D96FF", key="add_color")
    if st.button("Add node"):
        if new_label.strip():
            add_node(new_label.strip(), parent_choice, node_color)
            st.rerun()
        else:
            st.warning("Enter a label first.")

with st.sidebar.expander("✏️ Rename Node"):
    rename_choice = st.selectbox(
        "Select node", options=list(id_to_label.keys()),
        format_func=lambda x: id_to_label[x], key="rename_select",
    )
    rename_text = st.text_input("New label", key="rename_text")
    if st.button("Rename"):
        if rename_text.strip():
            rename_node(rename_choice, rename_text.strip())
            st.rerun()

with st.sidebar.expander("🗑️ Delete Node"):
    delete_choice = st.selectbox(
        "Select node", options=list(id_to_label.keys()),
        format_func=lambda x: id_to_label[x], key="delete_select",
    )
    if st.button("Delete node (and its branch)"):
        delete_node(delete_choice)
        st.rerun()

st.sidebar.divider()
st.sidebar.subheader("💾 Save / Load")

st.sidebar.download_button(
    "Download mind map (.json)",
    data=export_json(),
    file_name="mindmap.json",
    mime="application/json",
)

uploaded = st.sidebar.file_uploader("Load mind map (.json)", type=["json"])
if uploaded is not None:
    try:
        data = json.load(uploaded)
        load_json(data)
        st.sidebar.success("Loaded!")
        st.rerun()
    except Exception as e:
        st.sidebar.error(f"Failed to load: {e}")

if st.sidebar.button("🔄 Reset to blank map"):
    for key in ("nodes", "edges", "root_id"):
        del st.session_state[key]
    st.rerun()

# ----------------------------------------------------------------------
# Main graph view
# ----------------------------------------------------------------------
st.title("🧠 Mind Map Creator & Editor")
st.caption("Drag nodes to rearrange. Use the sidebar to add, rename, delete, save, or load.")

agraph_nodes = [
    Node(
        id=nid,
        label=n["label"],
        size=n.get("size", 20),
        color=n.get("color", "#4D96FF"),
    )
    for nid, n in st.session_state.nodes.items()
]
agraph_edges = [Edge(source=e["source"], target=e["target"]) for e in st.session_state.edges]

config = Config(
    width="100%",
    height=650,
    directed=True,
    physics=True,
    hierarchical=False,
    nodeHighlightBehavior=True,
    highlightColor="#F7A72B",
    collapsible=False,
)

agraph(nodes=agraph_nodes, edges=agraph_edges, config=config)

st.divider()
with st.expander("📋 Raw data (nodes & edges)"):
    st.json({"nodes": st.session_state.nodes, "edges": st.session_state.edges})
