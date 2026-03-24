import os
from graph.outline_graph import build_outline_graph
from graph.doc_graph import build_doc_graph

os.makedirs('assets', exist_ok=True)

print("Generating outline_graph.png...")
outline_graph = build_outline_graph()
with open("assets/outline_graph.png", "wb") as f:
    f.write(outline_graph.get_graph().draw_mermaid_png())

print("Generating doc_graph.png...")
doc_graph = build_doc_graph()
with open("assets/doc_graph.png", "wb") as f:
    f.write(doc_graph.get_graph().draw_mermaid_png())

print("Done!")
