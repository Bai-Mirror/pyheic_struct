# pyheic_struct/main.py

from heic_file import HEICFile
import os

def analyze_and_reconstruct(filename: str):
    print(f"--- Analyzing {filename} ---")
    
    # 检查文件是否存在
    if not os.path.exists(filename):
        print(f"Error: File not found at {filename}")
        print("="*40 + "\n")
        return

    heic_file = HEICFile(filename)

    # 重建主图像
    reconstructed_image = heic_file.reconstruct_primary_image()
    
    if reconstructed_image:
        # 获取不带扩展名的基本文件名
        base_filename = os.path.splitext(filename)[0]
        
        # 1. 保存为高质量的有损格式 (JPEG)
        try:
            jpeg_filename = f"{base_filename}_reconstructed.jpg"
            reconstructed_image.save(jpeg_filename, "JPEG", quality=95)
            print(f"Successfully saved lossy JPEG to: {jpeg_filename}")
        except Exception as e:
            print(f"Could not save JPEG file: {e}")

        # 2. 保存为无损格式 (PNG)
        try:
            png_filename = f"{base_filename}_reconstructed.png"
            reconstructed_image.save(png_filename, "PNG")
            print(f"Successfully saved lossless PNG to: {png_filename}")
        except Exception as e:
            print(f"Could not save PNG file: {e}")
            
    else:
        print("Failed to reconstruct image.")

    print("\n" + "="*40 + "\n")

def main():
    # 确保文件路径正确
    apple_file = 'apple.HEIC'
    samsung_file = 'samsung.heic'
    
    analyze_and_reconstruct(apple_file)
    analyze_and_reconstruct(samsung_file)

if __name__ == "__main__":
    main()