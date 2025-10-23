import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_EXAMPLE = ROOT_DIR / "examples" / "samsung_apple_compatible.HEIC"

# --- Hex Dump Utility ---
def hexdump(data, length=16):
    """Creates a formatted hex dump of a byte string."""
    results = []
    for i in range(0, len(data), length):
        chunk = data[i:i + length]
        
        # 1. Offset
        offset = f"{i:08x}  "
        
        # 2. Hex values
        hex_part = " ".join(f"{b:02x}" for b in chunk)
        hex_part = hex_part.ljust(length * 3 - 1) # Pad to align
        
        # 3. ASCII representation
        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        
        results.append(f"{offset}{hex_part}  |{ascii_part}|")
    return "\n".join(results)
# --- End Utility ---


filename = os.environ.get("HEIC_SAMPLE", str(DEFAULT_EXAMPLE))

if not os.path.exists(filename):
    print(f"Error: File not found: {filename}")
    print("Set HEIC_SAMPLE environment variable or place the sample under examples/.")
else:
    try:
        with open(filename, 'rb') as f:
            # Read the first 512 bytes (enough to see the ftyp and meta headers)
            file_header_data = f.read(512)
            
        print(f"--- Hex Dump for {filename} (First 512 Bytes) ---")
        print(hexdump(file_header_data))
        print("="*60)
        
    except Exception as e:
        print(f"An error occurred while reading the file: {e}")
