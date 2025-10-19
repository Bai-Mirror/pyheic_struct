from parser import parse_boxes

def main():
    # Test with the Apple HEIC file
    print("--- Analyzing Apple HEIC file ---")
    try:
        with open('apple.heic', 'rb') as f:
            top_level_boxes = parse_boxes(f)
            for box in top_level_boxes:
                print(box)
    except FileNotFoundError:
        print("Error: apple.heic not found.")
    
    print("\n" + "="*40 + "\n")

    # Test with the Samsung HEIC file
    print("--- Analyzing Samsung HEIC file ---")
    try:
        with open('samsung.heic', 'rb') as f:
            top_level_boxes = parse_boxes(f)
            for box in top_level_boxes:
                print(box)
    except FileNotFoundError:
        print("Error: samsung.heic not found.")


if __name__ == "__main__":
    main()