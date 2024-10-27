import py5
import ipywidgets as widgets
from IPython.display import display
import numpy as np

# Create interactive controls
size_slider = widgets.IntSlider(
    value=20,
    min=5,
    max=50,
    description='Size:',
    continuous_update=True
)

speed_slider = widgets.FloatSlider(
    value=1.0,
    min=0.1,
    max=3.0,
    step=0.1,
    description='Speed:',
    continuous_update=True
)

color_picker = widgets.ColorPicker(
    concise=False,
    description='Color:',
    value='#0000ff',
    style={'description_width': 'initial'}
)

trail_checkbox = widgets.Checkbox(
    value=True,
    description='Leave Trail',
    style={'description_width': 'initial'}
)

# Display controls
controls = widgets.VBox([size_slider, speed_slider, color_picker, trail_checkbox])
display(controls)

def settings():
    py5.size(400, 400)

def setup():
    py5.background(240)

def draw():
    if not trail_checkbox.value:
        py5.background(240)
    
    # Get current control values
    size = size_slider.value
    speed = speed_slider.value
    color = color_picker.value
    
    # Convert hex color to RGB
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    
    # Create movement using noise
    t = py5.frame_count * 0.02 * speed
    x = py5.noise(t) * py5.width
    y = py5.noise(t + 5) * py5.height
    
    # Draw
    py5.fill(r, g, b, 100)
    py5.no_stroke()
    py5.circle(x, y, size)
    
    # Add mouse interaction
    if py5.is_mouse_pressed:
        py5.circle(py5.mouse_x, py5.mouse_y, size)

# Run the sketch
py5.run_sketch(block=False)