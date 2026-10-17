"""Small dependency-free readers for explicit upstream tables and clinical XLSX.

XLSX values are read from stored cells, including shared/inline strings and
cached formula values. No formulas are evaluated or dates invented. Numeric
Excel dates are rejected by canonical date validation unless an explicit
clinical context supplies their meaning. Row selection belongs to clinical.
"""
import csv
import gzip
import json
from pathlib import Path, PurePosixPath
import posixpath
from xml.etree import ElementTree as ET
from zipfile import ZipFile


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def table(path, delimiter='\t'):
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt',encoding='utf-8-sig') as stream:
        return list(csv.DictReader((line for line in stream if not line.startswith('#')),delimiter=delimiter))


def xlsx(path):
    ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
    with ZipFile(path) as archive:
        strings=[]
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings=[''.join(e.itertext()) for e in ET.fromstring(archive.read('xl/sharedStrings.xml')).findall('s:si',ns)]
        rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))}
        sheets={}
        for sheet in ET.fromstring(archive.read('xl/workbook.xml')).findall('s:sheets/s:sheet',ns):
            rel=sheet.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']
            target=rels[rel]
            member=posixpath.normpath(target.lstrip('/') if target.startswith('/') else str(PurePosixPath('xl')/target))
            rows=[]
            for row in ET.fromstring(archive.read(member)).findall('s:sheetData/s:row',ns):
                cells={}
                for cell in row.findall('s:c',ns):
                    column=''.join(c for c in cell.attrib['r'] if c.isalpha())
                    value=cell.find('s:v',ns);text=value.text if value is not None else None
                    kind=cell.attrib.get('t')
                    if kind=='s' and text is not None:text=strings[int(text)]
                    elif kind=='inlineStr':text=''.join(cell.find('s:is',ns).itertext())
                    elif kind not in ['str','e'] and text is not None:
                        text=float(text) if '.' in text else int(text)
                    cells[column]=text
                rows.append(cells)
            if rows:
                headers=rows[0]
                sheets[sheet.attrib['name']]=[{str(name):row.get(col) for col,name in headers.items() if name is not None} for row in rows[1:]]
        return sheets
