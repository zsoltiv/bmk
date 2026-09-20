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

import pymupdf

from .redactor import Redactor, TextExtractKind
from .utils import rawdict as rd
from .utils import regex as reg


class UnicreditRedactor(Redactor):
    def __init__(self, doc: pymupdf.Document, output_filename: str, extract_kind: TextExtractKind = TextExtractKind.RAWDICT) -> None:
        super().__init__(doc, output_filename, extract_kind)
        self.spendings_start_page_idx = -1

    def footer_redact_sensitive_value(self, page: pymupdf.Page, page_text, substr) -> bool:
        text_idx = rd.block_idx_by_text(page_text, substr)
        if text_idx == -1:
            return False

        # következő blokkban van az érték
        value_idx = text_idx + 1
        if value_idx >= len(page_text):
            return False

        try:
            rect_to_redact = pymupdf.Rect(page_text[value_idx]['lines'][0]['spans'][0]['bbox'])
            page.add_redact_annot(rect_to_redact, fill=self.REDACTION_COLOR)
            return True
        except IndexError:
            return False

    def redact_iban_and_account_numbers(self, page: pymupdf.Page, page_text) -> bool:
        iban_and_account_idx = rd.block_idx_by_text(page_text, 'IBAN')
        if iban_and_account_idx == -1:
            return False

        values_idx = iban_and_account_idx + 1
        if values_idx >= len(page_text):
            return False

        try:
            account_rect = pymupdf.Rect(page_text[values_idx]['lines'][0]['spans'][0]['bbox'])
            iban_rect = pymupdf.Rect(page_text[values_idx]['lines'][1]['spans'][0]['bbox'])

            page.add_redact_annot(account_rect, fill=self.REDACTION_COLOR)
            page.add_redact_annot(iban_rect, fill=self.REDACTION_COLOR)
            return True
        except IndexError:
            return False

    def redact_initial_balance(self, page: pymupdf.Page, page_text) -> bool:
        initial_balance_text_idx = rd.block_idx_by_text(page_text, 'Nyitó egyenleg')
        if initial_balance_text_idx == -1:
            return False

        initial_balance_idx = initial_balance_text_idx + 1
        if initial_balance_idx >= len(page_text):
            return False

        try:
            rect_to_redact = pymupdf.Rect(page_text[initial_balance_idx]['lines'][3]['spans'][0]['bbox'])
            page.add_redact_annot(rect_to_redact, fill=self.REDACTION_COLOR)
            return True
        except IndexError:
            return False

    def has_spendings(self, page_text) -> bool:
        idx = rd.block_idx_by_text(page_text, 'Terhelések')
        return idx != -1

    def redact_spendings(self, page: pymupdf.Page, page_text, page_idx: int) -> None:
        spendings_block_idx = rd.block_idx_by_regex(page_text, reg.GENERIC_SPENDING_PATTERN)
        if spendings_block_idx == -1:
            return

        found_spendings_marker = False
        should_keep = lambda text: reg.MONTH_DAY_PATTERN.match(text) or reg.DATE_PATTERN.match(text) or text.isspace()

        for line in page_text[spendings_block_idx]['lines']:
            for span in line['spans']:
                text = rd.extract_span_text(span)

                if 'Terhelések' in text:
                    found_spendings_marker = True
                    continue

                is_in_spendings_section = found_spendings_marker or (page_idx > self.spendings_start_page_idx and self.spendings_start_page_idx != -1)

                if not is_in_spendings_section:
                    continue

                if reg.GENERIC_SPENDING_PATTERN.match(text):
                    chars_to_redact = span['chars'][1:]
                    if chars_to_redact:
                        page.add_redact_annot(rd.compute_substring_bounding_box(chars_to_redact), fill=self.REDACTION_COLOR)

                elif not should_keep(text):
                    page.add_redact_annot(span['bbox'], fill=self.REDACTION_COLOR)

    def process_page(self, page: pymupdf.Page, page_idx: int, extracted_text) -> None:
        page_text = [b for b in extracted_text['blocks'] if b['type'] == 0]

        if self.spendings_start_page_idx == -1 and self.has_spendings(page_text):
            self.spendings_start_page_idx = page_idx

        self.footer_redact_sensitive_value(page, page_text, 'Terhelések összesen')
        self.footer_redact_sensitive_value(page, page_text, 'Záró egyenleg')
        self.redact_iban_and_account_numbers(page, page_text)
        self.redact_initial_balance(page, page_text)

        if self.spendings_start_page_idx != -1:
            self.redact_spendings(page, page_text, page_idx)
