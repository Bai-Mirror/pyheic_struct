from base import Box
from parser import parse_boxes
from heic_types import ItemLocationBox
from typing import List
import os

def print_box_tree(boxes: List[Box], indent: int = 0):
    for box in boxes:
        print("  " * indent + str(box))
        
        if isinstance(box, ItemLocationBox):
            for loc in box.locations[:5]:
                print("  " * (indent + 1) + str(loc))
            if len(box.locations) > 5:
                print("  " * (indent + 1) + f"... and {len(box.locations) - 5} more locations")

        if box.children:
            print_box_tree(box.children, indent + 1)

def main():
    # Test with the Apple HEIC file
    print("--- Analyzing Apple HEIC file ---")
    try:
        with open('apple.heic', 'rb') as f:
            file_size = os.fstat(f.fileno()).st_size
            top_level_boxes = parse_boxes(f, file_size)
            print_box_tree(top_level_boxes)
    except FileNotFoundError:
        print("Error: apple.heic not found.")
    
    print("\n" + "="*40 + "\n")

    # Test with the Samsung HEIC file
    print("--- Analyzing Samsung HEIC file ---")
    try:
        with open('samsung.heic', 'rb') as f:
            file_size = os.fstat(f.fileno()).st_size
            top_level_boxes = parse_boxes(f, file_size)
            print_box_tree(top_level_boxes)
    except FileNotFoundError:
        print("Error: samsung.heic not found.")


if __name__ == "__main__":
    main()