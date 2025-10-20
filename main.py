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

    # 3. 尝试提取并保存缩略图
    thumbnail_data = heic_file.get_thumbnail_data()
    if thumbnail_data:
        try:
            # 缩略图数据通常是 JPEG 或 HEIC 格式
            # 我们先假设它是 JPEG 并以此后缀保存
            thumb_filename = f"{base_filename}_thumbnail.jpg"
            with open(thumb_filename, "wb") as f_thumb:
                f_thumb.write(thumbnail_data)
            print(f"Successfully saved thumbnail data to: {thumb_filename}")
            print(f" (Note: This file might be a JPEG or a small HEIC. Try opening it.)")
        except Exception as e:
            print(f"Could not save thumbnail file: {e}")
    else:
        print("No thumbnail data found or extracted.")


    print("\n" + "="*40 + "\n")

def main():
    # 确保文件路径正确
    apple_file = 'apple.HEIC'
    samsung_file = 'samsung.heic'
    
    analyze_and_reconstruct(apple_file)
    analyze_and_reconstruct(samsung_file)

if __name__ == "__main__":
    main()