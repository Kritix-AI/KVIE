import os
from PIL import Image

logo_path = os.path.abspath("public/logo.png")
if not os.path.exists(logo_path):
    print("Logo not found at", logo_path)
    exit(1)

img = Image.open(logo_path).convert("RGBA")

# Mipmap sizes for launcher icons (size, foreground_size)
densities = {
    "mipmap-mdpi": (48, 108),
    "mipmap-hdpi": (72, 162),
    "mipmap-xhdpi": (96, 216),
    "mipmap-xxhdpi": (144, 324),
    "mipmap-xxxhdpi": (192, 432),
}

res_dir = os.path.abspath("src-tauri/gen/android/app/src/main/res")

for folder, (size, fg_size) in densities.items():
    folder_path = os.path.join(res_dir, folder)
    os.makedirs(folder_path, exist_ok=True)
    
    # 1. Standard ic_launcher.png
    launcher = img.resize((size, size), Image.Resampling.LANCZOS)
    launcher.save(os.path.join(folder_path, "ic_launcher.png"), "PNG")
    
    # 2. Round ic_launcher_round.png
    launcher.save(os.path.join(folder_path, "ic_launcher_round.png"), "PNG")
    
    # 3. Foreground ic_launcher_foreground.png (scaled inside canvas for adaptive icon)
    fg_canvas = Image.new("RGBA", (fg_size, fg_size), (0, 0, 0, 0))
    # Place logo in center with 70% padding for adaptive icon safe zone
    icon_inner_size = int(fg_size * 0.72)
    inner_logo = img.resize((icon_inner_size, icon_inner_size), Image.Resampling.LANCZOS)
    offset = (fg_size - icon_inner_size) // 2
    fg_canvas.paste(inner_logo, (offset, offset), inner_logo)
    fg_canvas.save(os.path.join(folder_path, "ic_launcher_foreground.png"), "PNG")
    print(f"Generated icons for {folder}: {size}x{size} & fg {fg_size}x{fg_size}")

# Also update src-tauri/icons/icon.png
tauri_icon_path = os.path.abspath("src-tauri/icons/icon.png")
if os.path.exists(os.path.dirname(tauri_icon_path)):
    img.resize((512, 512), Image.Resampling.LANCZOS).save(tauri_icon_path, "PNG")
    print("Updated src-tauri/icons/icon.png")

print("\nSuccessfully updated all Android app launcher icons with original logo!")
