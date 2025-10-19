# pyheic_struct/main.py

from heic_file import HEICFile

def analyze_file(filename: str):
    print(f"--- Analyzing {filename} ---")
    heic_file = HEICFile(filename)

    # List all available items in the file
    heic_file.list_items()

    # Get the ID of the primary image
    primary_id = heic_file.get_primary_item_id()
    if primary_id:
        print(f"The primary item ID is: {primary_id}")

        # Get the primary image dimensions
        size = heic_file.get_image_size(primary_id)
        if size:
            print(f"Primary image dimensions (WxH): {size[0]} x {size[1]}")
        
        # --- Use our new feature! ---
        grid_layout = heic_file.get_grid_layout()
        if grid_layout:
            print(f"Primary image is a grid composed of these item IDs: {grid_layout}")
            # Optional: Get size of the first tile to see the difference
            first_tile_id = grid_layout[0]
            tile_size = heic_file.get_image_size(first_tile_id)
            if tile_size:
                print(f"  - Size of the first tile (ID {first_tile_id}): {tile_size[0]} x {tile_size[1]}")

    print("\n" + "="*40 + "\n")

def main():
    analyze_file('apple.HEIC')
    analyze_file('samsung.heic')

if __name__ == "__main__":
    main()