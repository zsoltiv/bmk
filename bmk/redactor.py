'''
 This file is part of bmk.

bmk is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License as published by the Free Software Foundation,
either version 3 of the License, or (at your option) any later version.

bmk is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or
FITNESS FOR A PARTICULAR PURPOSE.
See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with bmk.
If not, see <https://www.gnu.org/licenses/>.
'''

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import ClassVar, Self, final

import pymupdf

"""
mymupdf.Page.get_text() `option` paraméterét szabja meg,
a `process_page` `text_page` paramétere kapja a feldolgozott szöveget
"""
TextExtractKind = StrEnum('TextExtractKind', [
    ('TEXT', 'text'),
    ('BLOCKS', 'blocks'),
    ('DICT', 'dict'),
    ('RAWDICT', 'rawdict'),
    ('WORDS','words')])

class Redactor(ABC):

    REDACTION_COLOR: ClassVar[tuple[int, int, int]] = (0, 0, 0)

    def __init__(self, doc: pymupdf.Document, output_filename: str, extract_kind: TextExtractKind = TextExtractKind.TEXT) -> None:
        self.doc: pymupdf.Document = doc
        self.output_filename: str = output_filename
        self.extract_kind: TextExtractKind = extract_kind
        self.total_pages: int = len(doc)

    @abstractmethod
    def process_page(self, page: pymupdf.Page, page_idx: int, extracted_text) -> None:
        """Az öröklő osztály definiálja, hogy milyen módon dolgozza fel a PDF oldalakat (layout függő)"""

    def postprocess(self):
        """Ebben futtathatunk kódot a `process_page` hívások után"""

    @final
    def process_pages(self) -> None:
        for page_idx, page in enumerate(self.doc.pages()):
            page_text = page.get_text(self.extract_kind)
            self.process_page(page, page_idx, page_text)
            print(f"{page_idx+1} of {self.total_pages} pages processed.", end=("\r" if page_idx+1 < self.total_pages else ""))
        self.postprocess()
        for page in self.doc.pages():
            self.finalize_page(page)

    @final
    def finalize_page(self, page: pymupdf.Page) -> None:
        page.apply_redactions()

    @final
    def __enter__(self) -> Self:
        return self

    @final
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None:
            self.doc.save(self.output_filename)
        self.doc.close()

    def __str__(self):
        return f"Redactor class for pdf files. This specific redactor class was initialized with:"\
               f"\n|-----> Derived class used={self.__class__}"\
               f"\n|-----> The document to process={self.doc.name}"\
               f"\n|-----> Name of the output file={self.output_filename}"\
               f"\n|-----> Extraction strategy used={self.extract_kind}"
