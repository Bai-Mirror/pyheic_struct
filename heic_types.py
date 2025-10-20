# pyheic_struct/heic_types.py

import struct
from base import Box, FullBox
from io import BytesIO
from typing import List # <-- 添加 List 导入

# --- 帮助函数 ---

def _read_int(data: bytes, pos: int, size: int) -> int:
    """Helper to read an integer of variable size."""
    if pos + size > len(data): return 0
    if size == 0: return 0
    if size == 1: return data[pos]
    if size == 2: return struct.unpack('>H', data[pos:pos+2])[0]
    if size == 4: return struct.unpack('>I', data[pos:pos+4])[0]
    if size == 8: return struct.unpack('>Q', data[pos:pos+8])[0]
    return 0

def _write_int(value: int, size: int) -> bytes:
    """Helper to write an integer of variable size."""
    if size == 0: return b''
    if size == 1: return struct.pack('>B', value)
    if size == 2: return struct.pack('>H', value)
    if size == 4: return struct.pack('>I', value)
    if size == 8: return struct.pack('>Q', value)
    return b''

# --- ItemLocation ---
class ItemLocation:
    def __init__(self, item_id):
        self.item_id = item_id
        # extents 存储 (absolute_offset, length)
        self.extents = [] 

    def __repr__(self):
        total_length = sum(ext[1] for ext in self.extents)
        return f"<ItemLocation ID={self.item_id} extents={len(self.extents)} total_size={total_length}>"

# --- ItemLocationBox ---
# ('iloc')
class ItemLocationBox(FullBox):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.locations: List[ItemLocation] = []
        self.offset_size = 0
        self.length_size = 0
        self.base_offset_size = 0
        self.index_size = 0
        self.item_count = 0
        super().__init__(size, box_type, offset, raw_data)
        
    def _post_parse_initialization(self):
        self._parse_locations()
        
    def _parse_locations(self):
        stream = self.raw_data[4:] 
        
        sizes = struct.unpack('>H', stream[0:2])[0]
        self.offset_size = (sizes >> 12) & 0x0F
        self.length_size = (sizes >> 8) & 0x0F
        self.base_offset_size = (sizes >> 4) & 0x0F
        
        if self.version == 1 or self.version == 2:
            self.index_size = sizes & 0x0F
        
        current_pos = 2 
        if self.version < 2:
            self.item_count = struct.unpack('>H', stream[2:4])[0]
            current_pos = 4
        else: 
            self.item_count = struct.unpack('>I', stream[2:6])[0]
            current_pos = 6

        for _ in range(self.item_count):
            item_id = 0
            item_id_size = 2 if self.version < 2 else 4
            if current_pos + item_id_size > len(stream): break
            item_id = _read_int(stream, current_pos, item_id_size)
            current_pos += item_id_size
            
            loc = ItemLocation(item_id)

            if (self.version == 1 or self.version == 2) and current_pos + 2 <= len(stream):
                current_pos += 2 

            if current_pos + 2 > len(stream): break 
            current_pos += 2 
            
            base_offset = 0
            if self.base_offset_size > 0:
                if current_pos + self.base_offset_size > len(stream): break
                base_offset = _read_int(stream, current_pos, self.base_offset_size)
                current_pos += self.base_offset_size

            if current_pos + 2 > len(stream): break
            extent_count = struct.unpack('>H', stream[current_pos : current_pos+2])[0]
            current_pos += 2
            
            for __ in range(extent_count):
                if (self.version == 1 or self.version == 2) and self.index_size > 0:
                     if current_pos + self.index_size > len(stream): break
                     current_pos += self.index_size 

                if current_pos + self.offset_size > len(stream): break
                extent_offset = _read_int(stream, current_pos, self.offset_size)
                current_pos += self.offset_size

                if current_pos + self.length_size > len(stream): break
                extent_length = _read_int(stream, current_pos, self.length_size)
                current_pos += self.length_size
                
                loc.extents.append((base_offset + extent_offset, extent_length))
            self.locations.append(loc)

    # --- START FIX ---
    def rebuild_iloc_content(self, mdat_offset_delta: int, original_mdat_offset: int, original_mdat_size: int,
                                   meta_offset_delta: int, original_meta_offset: int, original_meta_size: int):
        """
        使用新的 mdat 和 meta 偏移增量 (deltas) 更新此盒的 extents，
        并重建 self.raw_data
        """
        print(f"Applying mdat delta ({mdat_offset_delta}) and meta delta ({meta_offset_delta}) to 'iloc' box...")
        content_stream = BytesIO()
        
        content_stream.write(self.build_full_box_header())
        
        sizes = (self.offset_size << 12) | (self.length_size << 8) | (self.base_offset_size << 4)
        if self.version == 1 or self.version == 2:
            sizes |= self.index_size
        content_stream.write(struct.pack('>H', sizes))

        if self.version < 2:
            content_stream.write(struct.pack('>H', len(self.locations)))
        else:
            content_stream.write(struct.pack('>I', len(self.locations)))

        for loc in self.locations:
            item_id_size = 2 if self.version < 2 else 4
            content_stream.write(_write_int(loc.item_id, item_id_size))
            
            if (self.version == 1 or self.version == 2):
                content_stream.write(struct.pack('>H', 0)) 
            
            content_stream.write(struct.pack('>H', 0)) 
            
            if self.base_offset_size > 0:
                content_stream.write(_write_int(0, self.base_offset_size)) 
                
            content_stream.write(struct.pack('>H', len(loc.extents)))
            
            for (original_offset, length) in loc.extents:
                if (self.version == 1 or self.version == 2) and self.index_size > 0:
                    content_stream.write(_write_int(0, self.index_size)) 
                
                # !!! 魔法发生的地方 !!!
                new_absolute_offset = original_offset
                original_mdat_end_offset = original_mdat_offset + original_mdat_size
                original_meta_end_offset = original_meta_offset + original_meta_size
                
                if original_offset == 0:
                    new_absolute_offset = 0 # 保持 0 偏移量
                
                # 检查偏移量是否落在 *原始* mdat 盒区域内
                elif (original_mdat_offset <= original_offset < original_mdat_end_offset):
                    # 这是一个指向 mdat 的偏移量，应用 mdat 增量
                    new_absolute_offset = original_offset + mdat_offset_delta
                    
                # pyheic_struct_副本/heic_types.py

                # 检查偏移量是否落在 *原始* meta 盒区域内
                elif (original_meta_offset <= original_offset < original_meta_end_offset):
                    # 这是一个指向 meta 内部的偏移量 (例如 EXIF)
                    # (*** 错误修正 ***) 
                    # 它只应该被 *meta 盒之前* 的数据增长所平移。
                    # 在我们的 builder.py 逻辑中, 'meta_offset_delta' 正是这个值 (即 ftyp 盒的增长)。
                    new_absolute_offset = original_offset + meta_offset_delta
                
                # else:
                    # 这是一个指向其他地方 (如 ftyp) 的偏移量，我们假设它不动
                    # new_absolute_offset 保持等于 original_offset
                
                # 最后的安全检查，防止打包负数
                if new_absolute_offset < 0:
                    print(f"  Warning: Calculated a negative offset ({new_absolute_offset}) for item {loc.item_id}. Setting to 0.")
                    new_absolute_offset = 0
                
                content_stream.write(_write_int(new_absolute_offset, self.offset_size))
                content_stream.write(_write_int(length, self.length_size))

        self.raw_data = content_stream.getvalue()
        print(" 'iloc' box content successfully rebuilt.")
    # --- END FIX ---

    def build_content(self) -> bytes:
        return self.raw_data

# --- ItemInfoEntry (DataClass) ---
class ItemInfoEntry:
    def __init__(self, item_id, item_type, item_name):
        self.item_id = item_id
        self.type = item_type # 4-char code like 'hvc1'
        self.name = item_name # UTF-8 string
    def __repr__(self):
        return f"<ItemInfoEntry ID={self.item_id} type='{self.type}' name='{self.name}'>"

# --- ItemInfoEntryBox ---
# ('infe')
class ItemInfoEntryBox(FullBox):
    """代表一个 'infe' 盒"""
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.item_id: int = 0
        self.item_protection_index: int = 0
        self.item_type: str = "" # 4-char code
        self.item_name: str = "" # UTF-8 string
        super().__init__(size, box_type, offset, raw_data)

    def _post_parse_initialization(self):
        stream = self.raw_data[4:]
        if not stream: return 
        
        pos = 0
        try:
            if self.version == 0 or self.version == 1:
                self.item_id = struct.unpack('>H', stream[pos:pos+2])[0]
                pos += 2
                self.item_protection_index = struct.unpack('>H', stream[pos:pos+2])[0]
                pos += 2
                self.item_type = "" 
                name_end = stream.find(b'\x00', pos)
                if name_end == -1: name_end = len(stream)
                self.item_name = stream[pos:name_end].decode('utf-8', errors='ignore')
                
            elif self.version == 2:
                # --- START FIX 3 (Parser) ---
                # 恢复为原始顺序 (ID, ProtIdx, Type) 以正确 *读取* samsung.heic
                self.item_id = struct.unpack('>I', stream[pos:pos+4])[0]
                pos += 4
                self.item_protection_index = struct.unpack('>H', stream[pos:pos+2])[0]
                pos += 2
                self.item_type = stream[pos:pos+4].decode('ascii').strip('\x00')
                pos += 4
                # --- END FIX 3 ---
                
                name_end = stream.find(b'\x00', pos)
                if name_end == -1: name_end = len(stream)
                self.item_name = stream[pos:name_end].decode('utf-8', errors='ignore')

            elif self.version == 3:
                self.item_id = struct.unpack('>H', stream[pos:pos+2])[0]
                pos += 2
                self.item_protection_index = struct.unpack('>H', stream[pos:pos+2])[0]
                pos += 2
                self.item_type = stream[pos:pos+4].decode('ascii').strip('\x00')
                pos += 4
                name_end = stream.find(b'\x00', pos)
                if name_end == -1: name_end = len(stream)
                self.item_name = stream[pos:name_end].decode('utf-8', errors='ignore')
                
        except (struct.error, IndexError) as e:
            print(f"Warning: Failed to parse 'infe' box (v{self.version}). Content may be truncated. Error: {e}")
            self.item_id = 0
            self.item_type = ""
            self.item_name = ""

    def build_content(self) -> bytes:
        content = BytesIO()
        content.write(self.build_full_box_header()) 
        
        item_name_bytes_to_write = self.item_name.encode('utf-8') + b'\x00'
        
        if self.version == 0 or self.version == 1:
            content.write(struct.pack('>H', self.item_id))
            content.write(struct.pack('>H', self.item_protection_index))
            content.write(item_name_bytes_to_write)
            
        elif self.version == 2:
            content.write(struct.pack('>I', self.item_id))
            content.write(struct.pack('>H', self.item_protection_index))
            # item_type 必须是 4 字节的 4CC，若不足则以 NUL 填充
            content.write(self.item_type.encode('ascii', errors='ignore')[:4].ljust(4, b'\x00'))
            content.write(item_name_bytes_to_write)
            
        elif self.version == 3:
            content.write(struct.pack('>H', self.item_id))
            content.write(struct.pack('>H', self.item_protection_index))
            content.write(self.item_type.encode('ascii').ljust(4, b'\x00'))
            content.write(item_name_bytes_to_write)
            
        return content.getvalue()

# --- ItemInfoBox ---
# ('iinf')
class ItemInfoBox(FullBox):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.entries: list[ItemInfoEntry] = []
        self.item_count: int = 0
        super().__init__(size, box_type, offset, raw_data)

    def _post_parse_initialization(self):
        for child_box in self.children:
            if isinstance(child_box, ItemInfoEntryBox):
                self.entries.append(
                    ItemInfoEntry(child_box.item_id, child_box.item_type, child_box.item_name)
                )
        
        stream = self.raw_data[4:] 
        try:
            if self.version == 0:
                if len(stream) < 2: return 
                self.item_count = struct.unpack('>H', stream[0:2])[0]
            else: 
                if len(stream) < 4: return 
                self.item_count = struct.unpack('>I', stream[0:4])[0]
        except struct.error:
             print("Warning: Could not parse 'iinf' header. Content may be truncated.")

    def build_content(self) -> bytes:
        header = BytesIO()
        header.write(self.build_full_box_header()) 
        
        infe_children = [c for c in self.children if c.type == 'infe']
        
        if self.version == 0:
            header.write(struct.pack('>H', len(infe_children)))
        else: 
            header.write(struct.pack('>I', len(infe_children)))
            
        # --- START FIX 2 ---
        # 之前是: children_data = super().build_content()
        # 我们需要调用 Box.build_content (祖父级)
        children_data = super(FullBox, self).build_content()
        # --- END FIX 2 ---
        
        return header.getvalue() + children_data

# --- PrimaryItemBox ---
# ('pitm')
class PrimaryItemBox(FullBox):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.item_id: int = 0
        super().__init__(size, box_type, offset, raw_data)

    def _post_parse_initialization(self):
        stream = self.raw_data[4:]
        if not stream: return
        
        try:
            if self.version == 0:
                self.item_id = struct.unpack('>H', stream[0:2])[0]
            else:
                self.item_id = struct.unpack('>I', stream[0:4])[0]
        except struct.error:
            print("Warning: Could not parse 'pitm' box.")

    def build_content(self) -> bytes:
        content = BytesIO()
        content.write(self.build_full_box_header()) 
        if self.version == 0:
            content.write(struct.pack('>H', self.item_id))
        else:
            content.write(struct.pack('>I', self.item_id))
        return content.getvalue()

# --- ImageSpatialExtentsBox ---
# ('ispe')
class ImageSpatialExtentsBox(FullBox):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.image_width: int = 0
        self.image_height: int = 0
        super().__init__(size, box_type, offset, raw_data)
        
    def _post_parse_initialization(self):
        stream = self.raw_data[4:]
        if len(stream) < 8: return 
        try:
            self.image_width = struct.unpack('>I', stream[0:4])[0]
            self.image_height = struct.unpack('>I', stream[4:8])[0]
        except struct.error:
            print("Warning: Could not parse 'ispe' box.")
        
    def __repr__(self):
        return f"<ImageSpatialExtentsBox width={self.image_width} height={self.image_height}>"
        
    def build_content(self) -> bytes:
        content = BytesIO()
        content.write(self.build_full_box_header()) 
        content.write(struct.pack('>I', self.image_width))
        content.write(struct.pack('>I', self.image_height))
        return content.getvalue()

# --- ItemPropertyAssociationEntry (DataClass) ---
class ItemPropertyAssociationEntry:
    def __init__(self, item_id, association_count):
        self.item_id = item_id
        self.association_count = association_count
        self.associations = []
    def __repr__(self):
        return f"<ItemPropertyAssociationEntry item_id={self.item_id} associations={self.associations}>"

# --- ItemPropertyAssociationBox ---
# ('ipma')
class ItemPropertyAssociationBox(FullBox):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.entries: dict[int, ItemPropertyAssociationEntry] = {}
        super().__init__(size, box_type, offset, raw_data)

    def _post_parse_initialization(self):
        self._parse_associations()

    def _parse_associations(self):
        stream = self.raw_data[4:]
        if len(stream) < 4: return
        
        try:
            entry_count = struct.unpack('>I', stream[0:4])[0]
            pos = 4
            item_id_size = 4 if self.version >= 1 else 2
            is_large_property_index = (self.flags & 1) == 1
            
            for _ in range(entry_count):
                if pos + item_id_size > len(stream): break
                item_id = _read_int(stream, pos, item_id_size)
                pos += item_id_size
                
                if pos + 1 > len(stream): break
                association_count = stream[pos]
                pos += 1
                
                entry = ItemPropertyAssociationEntry(item_id, association_count)
                for __ in range(association_count):
                    prop_size = 2 if is_large_property_index else 1
                    if pos + prop_size > len(stream): break
                    assoc_value = _read_int(stream, pos, prop_size)
                    property_index = assoc_value & (0x7FFF if prop_size == 2 else 0x7F)
                    pos += prop_size
                    if property_index > 0:
                        entry.associations.append(property_index)
                self.entries[item_id] = entry
        except struct.error:
            print("Warning: Failed to parse 'ipma' box. Content may be truncated.")

    def build_content(self) -> bytes:
        content = BytesIO()
        content.write(self.build_full_box_header()) 
        
        content.write(struct.pack('>I', len(self.entries))) 
        
        item_id_size = 4 if self.version >= 1 else 2
        is_large_property_index = (self.flags & 1) == 1
        
        for item_id, entry in self.entries.items():
            content.write(_write_int(item_id, item_id_size))
            content.write(struct.pack('>B', len(entry.associations))) 
            
            for assoc_index in entry.associations:
                prop_size = 2 if is_large_property_index else 1
                content.write(_write_int(assoc_index, prop_size))
                
        return content.getvalue()

# --- ItemPropertyContainerBox ---
# ('ipco')
class ItemPropertyContainerBox(Box):
    def _post_parse_initialization(self):
        pass 

# --- ItemPropertiesBox ---
# ('iprp')
class ItemPropertiesBox(Box):
    def _post_parse_initialization(self):
        pass 
        
    @property
    def ipco(self) -> ItemPropertyContainerBox | None:
        for child in self.children:
            if isinstance(child, ItemPropertyContainerBox): return child
        return None
    @property
    def ipma(self) -> ItemPropertyAssociationBox | None:
        for child in self.children:
            if isinstance(child, ItemPropertyAssociationBox): return child
        return None

# --- ItemReferenceEntry (DataClass) ---
class ItemReferenceEntry:
    def __init__(self, from_id, to_ids):
        self.from_item_id = from_id
        self.to_item_ids = to_ids
    def __repr__(self):
        return f"<ItemReferenceEntry from={self.from_item_id} to={self.to_item_ids}>"

# --- ItemReferenceBox ---
# ('iref')
class ItemReferenceBox(FullBox):
    def __init__(self, size: int, box_type: str, offset: int, raw_data: bytes):
        self.references: dict[str, dict[int, list[int]]] = {}
        super().__init__(size, box_type, offset, raw_data)

    def _post_parse_initialization(self):
        self._parse_references_from_children()
        
    def _parse_references_from_children(self):
        item_id_size = 4 if self.version == 1 else 2

        for ref_box in self.children:
            ref_box_type = ref_box.type
            self.references[ref_box_type] = {}
            
            stream = ref_box.raw_data[4:] 
            pos = 0
            
            if pos + item_id_size > len(stream):
                print(f"Warning: Truncated 'iref' child box '{ref_box_type}'. Skipping.")
                continue 

            try:
                if item_id_size == 4:
                    from_item_id = struct.unpack('>I', stream[pos:pos+4])[0]
                    pos += 4
                else:
                    from_item_id = struct.unpack('>H', stream[pos:pos+2])[0]
                    pos += 2
                
                if pos + 2 > len(stream):
                    print(f"Info: 'iref' child box '{ref_box_type}' for ID {from_item_id} has no references. Skipping.")
                    self.references[ref_box_type][from_item_id] = [] 
                    continue 
                    
                reference_count = struct.unpack('>H', stream[pos:pos+2])[0]
                pos += 2
            except struct.error as e:
                print(f"Error parsing 'iref' child box '{ref_box_type}': {e}. Skipping.")
                continue
            
            to_item_ids = []
            for _ in range(reference_count):
                if pos + item_id_size > len(stream): break
                to_id = _read_int(stream, pos, item_id_size)
                to_item_ids.append(to_id)
                pos += item_id_size
                
            self.references[ref_box_type][from_item_id] = to_item_ids

    def build_content(self) -> bytes:
        header = BytesIO()
        header.write(self.build_full_box_header())
        
        # --- START FIX 2 ---
        # 之前是: children_data = super().build_content()
        # 我们需要调用 Box.build_content (祖父级)
        children_data = super(FullBox, self).build_content()
        # --- END FIX 2 ---
        
        return header.getvalue() + children_data