# pyheic_struct/heic_types.py

import struct
from base import Box, FullBox
from io import BytesIO
from typing import List, Optional # <-- 添加 List, Optional 导入

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
        self.data_reference_index = 0
        self.base_offset = 0
        self.construction_method = 0
        self.extent_indices = []
        self.raw_extents = []  # (relative_offset, length)
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
                loc.construction_method = struct.unpack('>H', stream[current_pos:current_pos+2])[0]
                current_pos += 2 

            if current_pos + 2 > len(stream): break 
            loc.data_reference_index = struct.unpack('>H', stream[current_pos:current_pos+2])[0]
            current_pos += 2 
            
            base_offset = 0
            if self.base_offset_size > 0:
                if current_pos + self.base_offset_size > len(stream): break
                base_offset = _read_int(stream, current_pos, self.base_offset_size)
                current_pos += self.base_offset_size
            loc.base_offset = base_offset

            if current_pos + 2 > len(stream): break
            extent_count = struct.unpack('>H', stream[current_pos : current_pos+2])[0]
            current_pos += 2
            
            for __ in range(extent_count):
                if (self.version == 1 or self.version == 2) and self.index_size > 0:
                     if current_pos + self.index_size > len(stream): break
                     loc.extent_indices.append(_read_int(stream, current_pos, self.index_size))
                     current_pos += self.index_size 

                if current_pos + self.offset_size > len(stream): break
                extent_offset = _read_int(stream, current_pos, self.offset_size)
                current_pos += self.offset_size

                if current_pos + self.length_size > len(stream): break
                extent_length = _read_int(stream, current_pos, self.length_size)
                current_pos += self.length_size
                
                loc.raw_extents.append((extent_offset, extent_length))
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

        original_mdat_end_offset = original_mdat_offset + original_mdat_size
        original_meta_end_offset = original_meta_offset + original_meta_size

        def _adjust_absolute_offset(original_offset: int) -> int:
            if original_offset == 0:
                return 0
            if original_mdat_offset <= original_offset < original_mdat_end_offset:
                return original_offset + mdat_offset_delta
            if original_meta_offset <= original_offset < original_meta_end_offset:
                return original_offset + meta_offset_delta
            return original_offset

        for loc in self.locations:
            item_id_size = 2 if self.version < 2 else 4
            content_stream.write(_write_int(loc.item_id, item_id_size))
            
            if (self.version == 1 or self.version == 2):
                content_stream.write(struct.pack('>H', loc.construction_method & 0xFFFF))
            
            content_stream.write(struct.pack('>H', loc.data_reference_index))
            
            if self.base_offset_size > 0:
                new_base_offset = _adjust_absolute_offset(loc.base_offset)
                content_stream.write(_write_int(new_base_offset, self.base_offset_size))
            else:
                new_base_offset = 0
            
            extents_to_process = loc.raw_extents if loc.raw_extents else [
                (max(absolute_offset - loc.base_offset, 0), length) 
                for absolute_offset, length in loc.extents
            ]
            content_stream.write(struct.pack('>H', len(extents_to_process)))

            new_extents_absolute = []
            new_extents_relative = []
            new_extent_indices = []

            for idx, (original_relative_offset, length) in enumerate(extents_to_process):
                if (self.version == 1 or self.version == 2) and self.index_size > 0:
                    extent_index = loc.extent_indices[idx] if idx < len(loc.extent_indices) else 0
                    content_stream.write(_write_int(extent_index, self.index_size))
                    new_extent_indices.append(extent_index)
                
                original_absolute_offset = loc.base_offset + original_relative_offset
                new_absolute_offset = _adjust_absolute_offset(original_absolute_offset)
                
                if original_absolute_offset == 0:
                    new_absolute_offset = 0 # 保持 0 偏移量
                
                # 最后的安全检查，防止打包负数
                if new_absolute_offset < 0:
                    print(f"  Warning: Calculated a negative offset ({new_absolute_offset}) for item {loc.item_id}. Setting to 0.")
                    new_absolute_offset = 0

                if self.base_offset_size > 0:
                    new_relative_offset = new_absolute_offset - new_base_offset
                else:
                    new_relative_offset = new_absolute_offset

                if new_relative_offset < 0:
                    print(f"  Warning: Calculated a negative relative offset ({new_relative_offset}) for item {loc.item_id}. Setting to 0.")
                    new_relative_offset = 0
                    new_absolute_offset = new_base_offset
                
                content_stream.write(_write_int(new_relative_offset, self.offset_size))
                content_stream.write(_write_int(length, self.length_size))
                
                new_extents_absolute.append((new_absolute_offset, length))
                new_extents_relative.append((new_relative_offset, length))

            loc.base_offset = new_base_offset
            loc.extents = new_extents_absolute
            loc.raw_extents = new_extents_relative
            if new_extent_indices:
                loc.extent_indices = new_extent_indices

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
        self.content_type: Optional[str] = None
        self.content_encoding: Optional[str] = None
        self._has_protection_field: bool = True
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
                pos = min(name_end + 1, len(stream))

                if pos < len(stream):
                    ctype_end = stream.find(b'\x00', pos)
                    if ctype_end == -1: ctype_end = len(stream)
                    self.content_type = stream[pos:ctype_end].decode('utf-8', errors='ignore')
                    pos = min(ctype_end + 1, len(stream))

                if pos < len(stream):
                    cenc_end = stream.find(b'\x00', pos)
                    if cenc_end == -1: cenc_end = len(stream)
                    self.content_encoding = stream[pos:cenc_end].decode('utf-8', errors='ignore')
                    pos = min(cenc_end + 1, len(stream))
                
            elif self.version == 2:
                self.item_id = struct.unpack('>I', stream[pos:pos+4])[0]
                pos += 4

                remaining = len(stream) - pos
                self._has_protection_field = False
                if remaining >= 6:
                    candidate_protection = struct.unpack('>H', stream[pos:pos+2])[0]
                    candidate_type = stream[pos+2:pos+6]

                    if candidate_protection <= 0x00FF and b'\x00' not in candidate_type:
                        # 标准顺序: 2 字节保护索引 + 4 字节类型
                        self.item_protection_index = candidate_protection
                        self._has_protection_field = True
                        pos += 2
                        type_bytes = candidate_type
                        pos += 4
                    else:
                        # 三星文件: 直接写入类型 (如 'hvc1')，缺少保护索引
                        self.item_protection_index = 0
                        self._has_protection_field = False
                        type_bytes = stream[pos:pos+4]
                        pos += 4
                elif remaining >= 4:
                    # 某些三星文件缺少 2 字节的保护索引字段, 直接紧跟 4 字节类型
                    self.item_protection_index = 0
                    self._has_protection_field = False
                    type_bytes = stream[pos:pos+4]
                    pos += 4
                else:
                    # 无法获得完整的 4 字节类型
                    type_bytes = b''

                self.item_type = type_bytes.decode('ascii', errors='ignore').strip('\x00')

                name_end = stream.find(b'\x00', pos)
                if name_end == -1: name_end = len(stream)
                self.item_name = stream[pos:name_end].decode('utf-8', errors='ignore')
                pos = min(name_end + 1, len(stream))

                if pos < len(stream):
                    ctype_end = stream.find(b'\x00', pos)
                    if ctype_end == -1: ctype_end = len(stream)
                    self.content_type = stream[pos:ctype_end].decode('utf-8', errors='ignore')
                    pos = min(ctype_end + 1, len(stream))

                if pos < len(stream):
                    cenc_end = stream.find(b'\x00', pos)
                    if cenc_end == -1: cenc_end = len(stream)
                    self.content_encoding = stream[pos:cenc_end].decode('utf-8', errors='ignore')
                    pos = min(cenc_end + 1, len(stream))

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
                pos = min(name_end + 1, len(stream))

                if pos < len(stream):
                    ctype_end = stream.find(b'\x00', pos)
                    if ctype_end == -1: ctype_end = len(stream)
                    self.content_type = stream[pos:ctype_end].decode('utf-8', errors='ignore')
                    pos = min(ctype_end + 1, len(stream))

                if pos < len(stream):
                    cenc_end = stream.find(b'\x00', pos)
                    if cenc_end == -1: cenc_end = len(stream)
                    self.content_encoding = stream[pos:cenc_end].decode('utf-8', errors='ignore')
                    pos = min(cenc_end + 1, len(stream))
                
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
            if self._has_protection_field:
                content.write(struct.pack('>H', self.item_protection_index))
            # item_type 必须是 4 字节的 4CC，若不足则以 NUL 填充
            content.write(self.item_type.encode('ascii', errors='ignore')[:4].ljust(4, b'\x00'))
            content.write(item_name_bytes_to_write)
            if self.content_type is not None:
                content.write(self.content_type.encode('utf-8') + b'\x00')
            if self.content_encoding is not None:
                content.write(self.content_encoding.encode('utf-8') + b'\x00')

        elif self.version == 3:
            content.write(struct.pack('>H', self.item_id))
            content.write(struct.pack('>H', self.item_protection_index))
            content.write(self.item_type.encode('ascii').ljust(4, b'\x00'))
            content.write(item_name_bytes_to_write)
            if self.content_type is not None:
                content.write(self.content_type.encode('utf-8') + b'\x00')
            if self.content_encoding is not None:
                content.write(self.content_encoding.encode('utf-8') + b'\x00')
            
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
class ItemPropertyAssociation:
    def __init__(self, property_index: int, essential: bool):
        self.property_index = property_index
        self.essential = essential

    def __repr__(self):
        flag = '!' if self.essential else ''
        return f"{flag}{self.property_index}"


class ItemPropertyAssociationEntry:
    def __init__(self, item_id, association_count):
        self.item_id = item_id
        self.association_count = association_count
        self.associations: List[ItemPropertyAssociation] = []

    def __repr__(self):
        return (f"<ItemPropertyAssociationEntry item_id={self.item_id} "
                f"associations={[repr(a) for a in self.associations]}>")

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
                    essential_flag = 0x8000 if prop_size == 2 else 0x80
                    property_index = assoc_value & (0x7FFF if prop_size == 2 else 0x7F)
                    is_essential = (assoc_value & essential_flag) != 0
                    pos += prop_size
                    if property_index > 0:
                        entry.associations.append(
                            ItemPropertyAssociation(property_index, is_essential)
                        )
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
            
            for assoc in entry.associations:
                prop_size = 2 if is_large_property_index else 1
                mask = 0x7FFF if prop_size == 2 else 0x7F
                essential_flag = 0x8000 if prop_size == 2 else 0x80
                assoc_value = assoc.property_index & mask
                if assoc.essential:
                    assoc_value |= essential_flag
                content.write(_write_int(assoc_value, prop_size))
                
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
