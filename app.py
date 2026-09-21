import gradio as gr
from tritowers_vision import extract_screen,recognize
def inspect_image(path):
    if not path:return None,None,{"unsupported_reason":"no_image"}
    extraction=extract_screen(path); result=recognize(extraction.rectified,extraction.corners,extraction.manual)
    return extraction.overlay,extraction.rectified,result.to_dict()
with gr.Blocks(title="TriTowers screen intake") as demo:
    gr.Markdown("# TriTowers screen intake\nEarly scaffold: screen extraction only. Real cabinet recognition accuracy is not established.")
    upload=gr.Image(type="filepath",label="Quiz-machine photo or screenshot"); inspect=gr.Button("Inspect",variant="primary")
    with gr.Row(): overlay=gr.Image(label="Detected screen"); rectified=gr.Image(label="Rectified screen")
    result=gr.JSON(label="Conservative recognition result"); inspect.click(inspect_image,upload,[overlay,rectified,result])
if __name__=="__main__":demo.launch()
