# In main.py
from heic_file import HEICFile

def analyze_file(filename: str):
    print(f"--- Analyzing {filename} ---")
    heic_file = HEICFile(filename)
    
    # List all available items in the file
    heic_file.list_items()
    
    # Get the ID of the primary image
    primary_id = heic_file.get_primary_item_id()
    if primary_id:
        print(f"\nThe primary item ID is: {primary_id}")
    
    print("\n" + "="*40 + "\n")

def main():
    analyze_file('apple.heic')
    analyze_file('samsung.heic')

if __name__ == "__main__":
    main()