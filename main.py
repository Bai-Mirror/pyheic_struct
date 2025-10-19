from heic_file import HEICFile

def main():
    print("--- Processing Samsung HEIC file ---")
    samsung_heic = HEICFile('samsung.heic')
    samsung_video_data = samsung_heic.get_motion_photo_data()
    
    if samsung_video_data:
        output_filename = 'samsung_motion_photo.mp4'
        with open(output_filename, 'wb') as f:
            f.write(samsung_video_data)
        print(f"Successfully extracted motion photo to '{output_filename}' ({len(samsung_video_data)} bytes)")

    print("\n" + "="*40 + "\n")

    print("--- Processing Apple HEIC file ---")
    apple_heic = HEICFile('apple.heic')
    apple_video_data = apple_heic.get_motion_photo_data()

    if apple_video_data:
        # This block should not be reached for Apple files
        print("Extracted embedded video from Apple file (this is unexpected).")
    else:
        print("No embedded motion photo found in Apple file, as expected.")


if __name__ == "__main__":
    main()