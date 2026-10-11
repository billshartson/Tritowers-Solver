"""Private JSON annotation validator/editor. It stores nothing server-side."""

import json
import gradio as gr

from tritowers_vision.annotation import AnnotationDocument, AnnotationError, blank_slot_config


def _check_json_depth(raw, maximum=64):
    depth = 0; quoted = False; escaped = False
    for char in raw:
        if quoted:
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif char == '"': quoted = False
        elif char == '"': quoted = True
        elif char in "[{":
            depth += 1
            if depth > maximum: raise AnnotationError("JSON nesting is too deep.")
        elif char in "]}": depth -= 1


def validate_annotation(payload):
    try:
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        if len(raw) > 2 * 1024 * 1024:
            return None, "Invalid annotation: JSON exceeds the 2 MB limit."
        _check_json_depth(raw)
        document = AnnotationDocument.from_json(raw)
        return document.to_dict(), "Valid annotation. Nothing was uploaded or saved by this tool."
    except RecursionError:
        return None, "Invalid annotation: JSON nesting is too deep."
    except (AnnotationError, TypeError, ValueError, AttributeError) as error:
        return None, f"Invalid annotation: {error}"


with gr.Blocks(title="Private TriTowers annotation validator") as annotation_demo:
    gr.Markdown("# Private annotation validator\nPaste/edit canonical JSON. This scaffold validates and returns JSON; it does not persist images or labels.")
    payload = gr.Code(label="Annotation JSON", language="json")
    with gr.Row():
        template = gr.Button("Blank 30-slot template")
        validate = gr.Button("Validate", variant="primary")
    output = gr.JSON(label="Validated canonical document")
    status = gr.Textbox(label="Status")
    template.click(lambda: json.dumps({"slots": blank_slot_config()}, indent=2), outputs=payload)
    validate.click(validate_annotation, payload, [output, status])

if __name__ == "__main__":
    annotation_demo.launch()
