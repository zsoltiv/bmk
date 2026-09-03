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

import re

import pymupdf

from .redactor import Redactor, TextExtractKind
from .utils import rawdict as rd


class OtpRedactor(Redactor):
    def __init__(self, doc: pymupdf.Document, output_filename: str, extract_kind: TextExtractKind = TextExtractKind.RAWDICT) -> None:
        super().__init__(doc, output_filename, extract_kind)

        self.redacted_initial_balance = False
        self.OTP_SPENDING_PATTERN = re.compile(r'\-\d+(?:\.\d+)?')
        self.OTP_DATE_PATTERN = re.compile(r'(\d{2}\.){2}\d{2}')


    def redact_account_number(self, page: pymupdf.Page, page_text) -> None:
        account_details_block_idx = rd.block_idx_by_text(page_text, 'SZÁMLASZÁM')
        if account_details_block_idx == -1:
            return

        for line_idx, line in enumerate(page_text[account_details_block_idx]['lines']):
            for span_idx, span in enumerate(line['spans']):
                text = rd.extract_span_text(span)
                if ('SZÁMLASZÁM' in text or 'IBAN' in text or 'BIC(SWIFT)KÓD' in text) and (span_idx + 1 < len(line['spans'])):
                    page.add_redact_annot(line['spans'][span_idx + 1]['bbox'], fill=self.REDACTION_COLOR)

    def redact_spendings(self, page: pymupdf.Page, page_text) -> None:
        new_transaction = False
        for block_idx, block in enumerate(page_text):
            for line_idx, line in enumerate(block['lines']):
                for span_idx, span in enumerate(line['spans']):
                    text = rd.extract_span_text(span)

                    if self.OTP_SPENDING_PATTERN.match(text):
                        chars_to_redact = span['chars'][1:]
                        page.add_redact_annot(rd.compute_substring_bounding_box(chars_to_redact), fill=self.REDACTION_COLOR)

                        new_transaction = True
                    elif new_transaction:
                        # a legközelebbi dátumig minden kitakarható
                        if self.OTP_DATE_PATTERN.fullmatch(text.strip()) or 'IDÕSZAK' in text or 'IDŐSZAK' in text:
                            new_transaction = False
                        else:
                            page.add_redact_annot(span['bbox'], fill=self.REDACTION_COLOR)


    def redact_total_spendings(self, page: pymupdf.Page, page_text) -> None:
        total_spendings_idx = rd.block_idx_by_text(page_text, 'TERHELÉSEK ÖSSZESEN')
        if total_spendings_idx == -1:
            return

        chars = page_text[total_spendings_idx]['lines'][1]['spans'][0]['chars']
        minus_sign_idx = next((i for i, char in enumerate(chars) if char['c'] == '-'), -1)
        if minus_sign_idx != -1:
            page.add_redact_annot(rd.compute_substring_bounding_box(chars[minus_sign_idx+1:]), fill=self.REDACTION_COLOR)



    def process_page(self, page: pymupdf.Page, page_idx: int, extracted_text) -> None:
        page_text = [b for b in extracted_text['blocks'] if b['type'] == 0]

        self.redact_account_number(page, page_text)
        self.redact_spendings(page, page_text)


        if not self.redacted_initial_balance:
            initial_balance_block_idx = rd.block_idx_by_text(page_text, 'NYITÓ EGYENLEG')
            if initial_balance_block_idx != -1:
                text_line_idx = rd.line_idx_by_text(page_text[initial_balance_block_idx], 'NYITÓ EGYENLEG')
                page.add_redact_annot(page_text[initial_balance_block_idx]['lines'][text_line_idx-1]['spans'][0]['bbox'], fill=self.REDACTION_COLOR)
                self.redacted_initial_balance = True

        final_balance_idx = rd.block_idx_by_text(page_text, 'ZÁRÓ EGYENLEG')
        if final_balance_idx != -1:
            try:
                page.add_redact_annot(page_text[final_balance_idx]['lines'][1]['spans'][0]['bbox'], fill=self.REDACTION_COLOR)
                self.redact_total_spendings(page, page_text)
            except IndexError:
                print(f"Unexpected final balance layout. Skipping over on page {page_idx}")
