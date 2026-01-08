"""
Synthetic diagram generator for testing vision-aware reranking.
Creates simple vehicle maintenance diagrams programmatically.
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import os

BASE_DIR = Path(__file__).parent.resolve()
DIAGRAMS_DIR = BASE_DIR / "data" / "diagrams"
DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)


def generate_engine_diagnostic_flowchart():
    """Generate a simple engine diagnostic flowchart."""
    img = Image.new('RGB', (800, 1000), color='white')
    draw = ImageDraw.Draw(img)
    
    # Try to use a better font, fall back to default
    try:
        font_large = ImageFont.truetype("arial.ttf", 24)
        font_medium = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 14)
    except:
        font_large = ImageFont.load_default()
        font_medium = ImageFont.load_default()
        font_small = ImageFont.load_default()
    
    # Title
    draw.text((250, 30), "Engine Won't Start", fill='black', font=font_large)
    draw.text((300, 60), "Diagnostic Flow", fill='black', font=font_medium)
    
    # Decision boxes
    boxes = [
        (300, 120, 500, 170, "Check Battery\nVoltage", 'lightblue'),
        (300, 220, 500, 270, "Battery OK?", 'lightyellow'),
        (100, 320, 280, 370, "Charge/Replace\nBattery", 'lightcoral'),
        (520, 320, 700, 370, "Check Starter\nMotor", 'lightgreen'),
        (520, 420, 700, 470, "Starter OK?", 'lightyellow'),
        (320, 520, 680, 570, "Check Fuel\nPump", 'lightblue'),
        (320, 620, 680, 670, "Check Spark\nPlugs", 'lightgreen'),
        (300, 750, 500, 800, "Engine Starts", 'lightgreen'),
    ]
    
    # Draw boxes
    for x1, y1, x2, y2, text, color in boxes:
        draw.rectangle([x1, y1, x2, y2], outline='black', fill=color, width=2)
        # Center text
        text_bbox = draw.textbbox((0, 0), text, font=font_small)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = x1 + (x2 - x1 - text_width) // 2
        text_y = y1 + (y2 - y1 - text_height) // 2
        draw.text((text_x, text_y), text, fill='black', font=font_small)
    
    # Draw arrows
    arrows = [
        ((400, 170), (400, 220)),  # Start to battery check
        ((400, 270), (190, 320)),  # No -> replace battery
        ((500, 270), (610, 320)),  # Yes -> check starter
        ((610, 370), (610, 420)),  # Starter check
        ((610, 470), (500, 520)),  # Check fuel
        ((500, 570), (500, 620)),  # Check spark
        ((500, 670), (400, 750)),  # To success
    ]
    
    for start, end in arrows:
        draw.line([start, end], fill='black', width=2)
        # Draw arrow head
        draw.polygon([end, (end[0]-5, end[1]-10), (end[0]+5, end[1]-10)], fill='black')
    
    # Add labels
    draw.text((420, 245), "No", fill='red', font=font_small)
    draw.text((510, 290), "Yes", fill='green', font=font_small)
    
    filepath = DIAGRAMS_DIR / "engine_diagnostic_flow.png"
    img.save(filepath)
    return filepath


def generate_brake_system_diagram():
    """Generate a simple brake system component diagram."""
    img = Image.new('RGB', (900, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_label = ImageFont.truetype("arial.ttf", 16)
    except:
        font_title = ImageFont.load_default()
        font_label = ImageFont.load_default()
    
    # Title
    draw.text((280, 30), "Brake System Components", fill='black', font=font_title)
    
    # Master cylinder
    draw.rectangle([100, 120, 250, 200], outline='black', fill='lightgray', width=3)
    draw.text((120, 150), "Master\nCylinder", fill='black', font=font_label)
    
    # Brake lines
    draw.line([(250, 160), (350, 160)], fill='red', width=4)
    draw.line([(350, 160), (350, 250)], fill='red', width=4)
    draw.line([(350, 250), (450, 250)], fill='red', width=4)
    draw.line([(350, 250), (250, 350)], fill='red', width=4)
    
    # Front brake
    draw.ellipse([450, 200, 600, 300], outline='black', fill='lightblue', width=3)
    draw.text((485, 240), "Front\nBrake", fill='black', font=font_label)
    
    # Rear brake
    draw.ellipse([150, 350, 300, 450], outline='black', fill='lightblue', width=3)
    draw.text((185, 390), "Rear\nBrake", fill='black', font=font_label)
    
    # Brake pedal
    draw.rectangle([50, 500, 150, 560], outline='black', fill='yellow', width=2)
    draw.text((65, 520), "Brake Pedal", fill='black', font=font_label)
    
    # Connection
    draw.line([(100, 500), (100, 400), (150, 300), (150, 200)], fill='gray', width=3)
    
    # Labels
    draw.text((260, 140), "Hydraulic\nFluid", fill='darkred', font=font_label)
    draw.text((720, 240), "Disc/Caliper", fill='black', font=font_label)
    # Manual arrow (older Pillow versions don't have arrow)
    draw.line([(720, 260), (600, 250)], fill='black', width=2)
    draw.polygon([(600, 250), (610, 245), (610, 255)], fill='black')
    
    filepath = DIAGRAMS_DIR / "brake_system_diagram.png"
    img.save(filepath)
    return filepath


def generate_cooling_system_diagram():
    """Generate a cooling system diagram."""
    img = Image.new('RGB', (900, 700), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_label = ImageFont.truetype("arial.ttf", 16)
    except:
        font_title = ImageFont.load_default()
        font_label = ImageFont.load_default()
    
    # Title
    draw.text((260, 30), "Engine Cooling System", fill='black', font=font_title)
    
    # Radiator
    draw.rectangle([100, 100, 300, 300], outline='black', fill='lightcyan', width=3)
    draw.text((150, 190), "Radiator", fill='black', font=font_label)
    
    # Engine block
    draw.rectangle([500, 150, 750, 400], outline='black', fill='lightgray', width=3)
    draw.text((570, 260), "Engine Block", fill='black', font=font_label)
    
    # Coolant flow (hot)
    draw.line([(625, 150), (625, 100), (300, 100)], fill='red', width=5)
    draw.text((420, 80), "Hot Coolant", fill='red', font=font_label)
    
    # Coolant flow (cool)
    draw.line([(100, 300), (100, 450), (500, 450), (500, 350)], fill='blue', width=5)
    draw.text((250, 460), "Cooled Coolant", fill='blue', font=font_label)
    
    # Water pump
    draw.ellipse([400, 400, 500, 500], outline='black', fill='lightyellow', width=3)
    draw.text((420, 440), "Water\nPump", fill='black', font=font_label)
    
    # Thermostat
    draw.rectangle([350, 100, 420, 140], outline='black', fill='orange', width=2)
    draw.text((350, 110), "Thermostat", fill='black', font=font_label)
    
    # Cooling fan
    draw.ellipse([150, 350, 250, 450], outline='black', fill='lightgreen', width=2)
    draw.text((170, 390), "Fan", fill='black', font=font_label)
    
    filepath = DIAGRAMS_DIR / "cooling_system_diagram.png"
    img.save(filepath)
    return filepath


def generate_electrical_system_diagram():
    """Generate an electrical system diagram."""
    img = Image.new('RGB', (1000, 600), color='white')
    draw = ImageDraw.Draw(img)
    
    try:
        font_title = ImageFont.truetype("arial.ttf", 28)
        font_label = ImageFont.truetype("arial.ttf", 14)
    except:
        font_title = ImageFont.load_default()
        font_label = ImageFont.load_default()
    
    # Title
    draw.text((280, 30), "Basic Electrical System", fill='black', font=font_title)
    
    # Battery
    draw.rectangle([100, 150, 250, 250], outline='black', fill='yellow', width=3)
    draw.text((140, 190), "Battery\n12V", fill='black', font=font_label)
    
    # Alternator
    draw.ellipse([100, 350, 250, 480], outline='black', fill='lightgreen', width=3)
    draw.text((140, 400), "Alternator", fill='black', font=font_label)
    
    # Starter motor
    draw.ellipse([450, 150, 600, 280], outline='black', fill='lightblue', width=3)
    draw.text((485, 205), "Starter\nMotor", fill='black', font=font_label)
    
    # Ignition
    draw.rectangle([450, 350, 600, 450], outline='black', fill='orange', width=2)
    draw.text((475, 390), "Ignition\nSystem", fill='black', font=font_label)
    
    # Fuse box
    draw.rectangle([750, 250, 900, 350], outline='black', fill='lightgray', width=2)
    draw.text((785, 290), "Fuse Box", fill='black', font=font_label)
    
    # Wiring (power)
    draw.line([(250, 200), (450, 215)], fill='red', width=4)  # Battery to starter
    draw.line([(250, 200), (750, 300)], fill='red', width=4)  # Battery to fuse box
    draw.line([(250, 400), (250, 250)], fill='red', width=4)  # Alternator to battery
    
    # Ground
    draw.line([(175, 480), (175, 520)], fill='black', width=3)
    draw.line([(155, 520), (195, 520)], fill='black', width=3)
    draw.line([(165, 530), (185, 530)], fill='black', width=3)
    draw.text((130, 535), "Ground", fill='black', font=font_label)
    
    filepath = DIAGRAMS_DIR / "electrical_system_diagram.png"
    img.save(filepath)
    return filepath


def generate_all_diagrams():
    """Generate all synthetic diagrams."""
    print("\n[Synthetic Diagrams] Generating test diagrams...")
    
    diagrams = {
        "engine_diagnostic_flow.png": generate_engine_diagnostic_flowchart,
        "brake_system_diagram.png": generate_brake_system_diagram,
        "cooling_system_diagram.png": generate_cooling_system_diagram,
        "electrical_system_diagram.png": generate_electrical_system_diagram,
    }
    
    generated = []
    for name, gen_func in diagrams.items():
        try:
            filepath = gen_func()
            generated.append(str(filepath))
            print(f"  ✓ Generated: {name}")
        except Exception as e:
            print(f"  ✗ Failed to generate {name}: {e}")
    
    print(f"[Synthetic Diagrams] Generated {len(generated)} diagrams in {DIAGRAMS_DIR}")
    return generated


if __name__ == "__main__":
    generate_all_diagrams()
