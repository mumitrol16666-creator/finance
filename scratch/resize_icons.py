import os
import sys

def resize_icon():
    source_img = r"C:\Users\usace\.gemini\antigravity\brain\ff070e80-b419-4baa-b35f-ced181036cf5\fintrack_app_icon_1780690151017.png"
    web_dir = r"c:\FinanceBot\mobile_app\web"
    
    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
        from PIL import Image

    print("Opening source image...")
    img = Image.open(source_img)

    # 1. Favicon (64x64)
    print("Generating favicon.png...")
    img.resize((64, 64), Image.Resampling.LANCZOS).save(os.path.join(web_dir, "favicon.png"), "PNG")

    # 2. Icons folder sizes
    icons_dir = os.path.join(web_dir, "icons")
    os.makedirs(icons_dir, exist_ok=True)

    sizes = {
        "Icon-192.png": (192, 192),
        "Icon-512.png": (512, 512),
        "Icon-maskable-192.png": (192, 192),
        "Icon-maskable-512.png": (512, 512)
    }

    for name, size in sizes.items():
        print(f"Generating icons/{name} ({size[0]}x{size[1]})...")
        img.resize(size, Image.Resampling.LANCZOS).save(os.path.join(icons_dir, name), "PNG")

    print("All icons generated successfully!")

if __name__ == "__main__":
    resize_icon()
