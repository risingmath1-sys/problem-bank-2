"""
hwp_xml_parser.py
XML-based HWP metadata parser using HWPML2X export.
Replaces COM-based paragraph scanning with pure XML analysis.

Key advantages:
1. Stealth: No HWP window activation needed for text analysis
2. Speed: 0.05s XML parse vs ~5s COM scanning
3. Accuracy: Direct tree structure, no cursor simulation

Usage:
    parser = HWPXMLParser(hwp_controller)
    result = parser.parse_file(hwp_file_path)
    # result = {
    #     'endnote_positions': [(note_num, para_idx), ...],
    #     'col_break_positions': [para_idx, ...],
    #     'problem_texts': {note_num: 'text...'},
    #     'endnote_texts': {note_num: '[학교/년/단원/난이도]'},
    # }
"""
import re
import xml.etree.ElementTree as ET
from typing import List, Dict, Tuple, Optional


class HWPXMLParser:
    """
    Parses HWP file content from HWPML2X XML export.
    Provides endnote positions, column breaks, and problem text
    without any UI/cursor interaction.
    """
    
    def __init__(self, controller=None):
        """
        controller: RobustHwpController instance (used only to export XML)
        """
        self.controller = controller
    
    def parse_file(self, hwp_path: str) -> Optional[Dict]:
        """
        Full pipeline: open HWP via controller, export XML, parse, close.
        Returns parsed metadata or None on failure.
        """
        if self.controller is None:
            raise ValueError("Controller required to export XML")
        
        # Open the HWP file
        doc_idx = self.controller.open(hwp_path)
        if doc_idx is None:
            return None
        
        try:
            # Export to HWPML2X XML (in-memory, no file write needed)
            xml_content = self.controller.get_xml()
            if not xml_content:
                return None
            return self.parse_xml_string(xml_content)
        finally:
            self.controller.close_doc(doc_idx)
    
    def parse_xml_string(self, xml_content: str) -> Dict:
        """
        Parse HWPML2X XML string and extract all problem metadata.
        Does NOT need a HWP controller - pure Python XML parsing.
        """
        # Strip the XML declaration (HWP often produces wrong encoding declaration)
        clean_xml = re.sub(r'<\?xml[^?]*\?>', '', xml_content, count=1).strip()
        
        root = ET.fromstring(clean_xml)
        section = root.find('.//SECTION')
        
        if section is None:
            return {}
        
        return self._parse_section(section)
    
    def parse_xml_file(self, xml_path: str) -> Dict:
        """Parse an HWPML2X XML file saved to disk."""
        with open(xml_path, 'r', encoding='utf-8') as f:
            return self.parse_xml_string(f.read())
    
    def _parse_section(self, section_el) -> Dict:
        """Extract all information from the SECTION element."""
        endnote_positions = []    # (note_num, para_idx)
        col_break_positions = []  # para_idx
        problem_texts = {}        # note_num -> problem text
        endnote_texts = {}        # note_num -> metadata tag text
        para_texts = {}           # para_idx -> plain text (for debugging)
        
        section_paras = section_el.findall('P')
        
        for para_idx, p_el in enumerate(section_paras):
            # Track column breaks
            if p_el.get('ColumnBreak') == 'true':
                col_break_positions.append(para_idx)
            
            # Collect plain text from this paragraph
            para_text = self._extract_para_text(p_el)
            if para_text:
                para_texts[para_idx] = para_text
            
            # Check for endnote anchor: P > TEXT > ENDNOTE > PARALIST > P > TEXT > AUTONUM
            for txt in p_el.findall('TEXT'):
                for endnote_el in txt.findall('ENDNOTE'):
                    pl = endnote_el.find('PARALIST')
                    if pl is None:
                        continue
                    first_p = pl.find('P')
                    if first_p is None:
                        continue
                    for inner_txt in first_p.findall('TEXT'):
                        for autonum in inner_txt.findall('AUTONUM'):
                            if autonum.get('NumberType') == 'Endnote':
                                note_num = int(autonum.get('Number', 0))
                                endnote_positions.append((note_num, para_idx))
                                
                                # Extract endnote text (the metadata tag like [학교/년/단원/난이도])
                                endnote_text = self._extract_endnote_text(endnote_el)
                                if endnote_text:
                                    endnote_texts[note_num] = endnote_text
        
        # Sort by para index (in case note_num order != para order)
        endnote_positions.sort(key=lambda x: x[1])
        
        # Now extract problem text ranges between each endnote anchor
        for i, (note_num, anchor_para) in enumerate(endnote_positions):
            if i + 1 < len(endnote_positions):
                end_para = endnote_positions[i + 1][1] - 1
            else:
                end_para = len(section_paras) - 1
            
            # Trim trailing blank paragraphs
            end_para = self._trim_trailing_blanks_xml(
                section_paras, anchor_para, end_para
            )
            
            text = self._extract_text_range(section_paras, anchor_para, end_para)
            problem_texts[note_num] = text
        
        return {
            'endnote_positions': endnote_positions,  # [(note_num, para_idx), ...]
            'col_break_positions': col_break_positions,
            'problem_texts': problem_texts,
            'endnote_texts': endnote_texts,
            'total_paras': len(section_paras),
        }
    
    def _extract_para_text(self, p_el, skip_endnote_content=True) -> str:
        """Extract plain text from a single P element, optionally skipping ENDNOTE content."""
        chars = []
        for txt in p_el.findall('TEXT'):
            for child in txt:
                if skip_endnote_content and child.tag == 'ENDNOTE':
                    continue  # Skip the embedded endnote body text
                if child.tag == 'CHAR':
                    if child.text:
                        chars.append(child.text)
                elif child.tag == 'EQUATION':
                    chars.append('[수식]')
                elif child.tag == 'IMAGE' or child.tag == 'PICTURE':
                    chars.append('[그림]')
        return ''.join(chars).strip()
    
    def _extract_endnote_text(self, endnote_el) -> str:
        """Extract all CHAR text from inside an ENDNOTE element (the metadata tag)."""
        chars = []
        for char in endnote_el.iter('CHAR'):
            if char.text:
                chars.append(char.text)
        return ''.join(chars).strip()
    
    def _trim_trailing_blanks_xml(self, section_paras, start_para: int, end_para: int) -> int:
        """
        Scans backward from end_para to find the last para with actual content.
        Much faster than COM-based trimming since text is already in memory.
        """
        # Build a metadata tag pattern to exclude from trailing content
        TAG_PATTERN = re.compile(r'^\[.*\/.*\]$')
        
        while end_para > start_para:
            p_el = section_paras[end_para]
            text = self._extract_para_text(p_el)
            
            # Skip blank paragraphs
            if not text:
                end_para -= 1
                continue
            
            # Skip metadata tag lines (next problem's tag accidentally captured)
            if TAG_PATTERN.match(text):
                end_para -= 1
                continue
            
            # Found real content
            break
        
        return end_para
    
    def _extract_text_range(self, section_paras, start_para: int, end_para: int) -> str:
        """Extract text from para_idx range [start_para, end_para] inclusive."""
        lines = []
        for p_el in section_paras[start_para:end_para + 1]:
            text = self._extract_para_text(p_el)
            if text:
                lines.append(text)
        return '\n'.join(lines)
    
    def detect_problem_type(self, text: str) -> str:
        """Detect if problem is multiple choice (객관식) or subjective (주관식)."""
        if any(sym in text for sym in ['①', '②', '③', '④', '⑤']):
            return '객관식'
        return '주관식'
    
    def parse_metadata_tag(self, tag_text: str) -> Dict:
        """Parse [학교/년도/단원/난이도] tag string."""
        meta = {'school': '', 'year': '', 'unit_code': '', 'difficulty': '', 'problem_type': ''}
        tag_text = tag_text.strip()
        if not (tag_text.startswith('[') and tag_text.endswith(']')):
            return meta
        
        content = tag_text[1:-1]
        parts = [p.strip() for p in content.split('/')]
        
        for p in parts:
            if any(k in p for k in ['고', '중', '학교']) and len(p) > 2:
                meta['school'] = p
            elif re.match(r'^\d{4}', p):
                meta['year'] = p[:4]
            elif re.match(r'^[A-Z][0-9]$', p):
                meta['unit_code'] = p
            elif p in ['상', '중', '하', 'A', 'B', 'C', 'D']:
                meta['difficulty'] = p
            elif any(k in p for k in ['객', '주', '단', '서']):
                if '객' in p:
                    meta['problem_type'] = '객관식'
                elif '서' in p:
                    meta['problem_type'] = '서답형'
                elif '단' in p:
                    meta['problem_type'] = '단답형'
                elif '주' in p:
                    meta['problem_type'] = '주관식'
        
        return meta


def build_pos_from_xml(endnote_positions, col_break_positions, section_para_count):
    """
    Convert XML-derived (note_num, para_idx) pairs to (list_id=0, para_idx, char=0) tuples
    compatible with HWP COM SetPos API.
    
    Returns: [(start_pos, end_pos), ...] for each problem
    where start_pos = (0, anchor_para - 1, 0) and
    end_pos = determined by col rules or next endnote.
    """
    problems = []
    n = len(endnote_positions)
    
    for i, (note_num, anchor_para) in enumerate(endnote_positions):
        start_pos = (0, max(0, anchor_para - 1), 0)
        
        if i + 1 < n:
            next_anchor = endnote_positions[i + 1][1]
            next_col_break = next((c for c in col_break_positions if c >= anchor_para), None)
            
            if next_col_break is not None and next_col_break < next_anchor:
                # Rule 2: next problem is in different column
                end_pos = (0, next_col_break - 1, 0)
            else:
                # Rule 1: same column
                end_pos = (0, max(anchor_para, next_anchor - 1), 0)
        else:
            # Rule 3: last problem
            end_pos = (0, section_para_count - 1, 0)
        
        problems.append({
            'note_num': note_num,
            'start_pos': list(start_pos),
            'end_pos': list(end_pos),
        })
    
    return problems


if __name__ == '__main__':
    import time
    
    XML_FILE = r'g:\문제은행\문제은행2\sample_hwpml.xml'
    
    t0 = time.time()
    parser = HWPXMLParser()
    result = parser.parse_xml_file(XML_FILE)
    
    print(f"Parse time: {time.time()-t0:.3f}s")
    print(f"Total paragraphs: {result.get('total_paras', 0)}")
    print(f"Endnote anchors: {len(result.get('endnote_positions', []))}")
    print(f"ColumnBreaks: {len(result.get('col_break_positions', []))}")
    print()
    
    print("=== Endnote positions (note_num, para_idx) ===")
    for note_num, para_idx in result.get('endnote_positions', [])[:10]:
        print(f"  Endnote {note_num:3d}: para_idx={para_idx}")
    
    print()
    print("=== Endnote metadata tags ===")
    for note_num, tag in list(result.get('endnote_texts', {}).items())[:5]:
        parsed = parser.parse_metadata_tag(tag)
        print(f"  Endnote {note_num}: {tag!r} -> {parsed}")
    
    print()
    print("=== Problem types ===")
    for note_num, text in list(result.get('problem_texts', {}).items())[:5]:
        ptype = parser.detect_problem_type(text)
        print(f"  Problem {note_num}: {ptype} | {text[:60]!r}")
    
    print()
    print("=== HWP Cursor Positions (Rule-based) ===")
    positions = build_pos_from_xml(
        result['endnote_positions'],
        result['col_break_positions'],
        result['total_paras']
    )
    for p in positions[:5]:
        print(f"  Problem {p['note_num']}: start={p['start_pos']} end={p['end_pos']}")
