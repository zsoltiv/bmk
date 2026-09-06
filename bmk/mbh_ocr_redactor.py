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

import os
import re
from concurrent.futures import ProcessPoolExecutor

import pymupdf

from .redactor import Redactor, TextExtractKind
from .utils import ocr
from .utils import rawdict as rd
from .utils import regex as reg

#def run_ocr(filename, pagenum, dpi, h, threshold):
#    with pymupdf.open(filename) as doc:
#        sm, scanned_doc = ocr.preprocess_scanned_page(doc[pagenum], dpi, h, threshold)
#        page_text = scanned_doc[0].get_text(option='rawdict')
#        page_text = [b for b in page_text['blocks'] if b['type'] == 0]
#        # Python tuple-t tudunk folyamatok között küldeni
#        pickleable_matrix = (sm.a, sm.b, sm.c, sm.d, sm.e, sm.f)
#        return pickleable_matrix, page_text

class MbhOcrRedactor(Redactor):
    def __init__(self, doc: pymupdf.Document, output_filename: str, extract_kind: TextExtractKind = TextExtractKind.RAWDICT) -> None:
        super().__init__(doc, output_filename, extract_kind)
        self.ocr_data = []

        with ProcessPoolExecutor(max_workers=os.cpu_count()) as executor:
            doc_names = [doc.name] * doc.page_count
            page_nums = list(range(doc.page_count))
            dpi = [300] * doc.page_count
            h = [20] * doc.page_count
            threshold = [190] * doc.page_count
            self.ocr_data = list(executor.map(ocr.process_worker, doc_names, page_nums, dpi, h, threshold))

        # Vesszőre is matchelünk, ne bízzunk túlságosan a Tesseract-ban
        self.DUMB_BALANCE_PATTERN = re.compile(r'\d+[.,]\d')
        self.DUMB_ACCOUNT_NUMBER_PATTERN = re.compile(r'\-?\d{5,8}')
        self.TEXT_START_PATTERN = re.compile('[A-Za-z]')

        self.found_initial_balance = False


    def attempt_redacting_topmost_initial_balance(self, orig_page: pymupdf.Page, ocr_page_text, scaling_matrix: pymupdf.Matrix) -> bool:
        initial_balance_text_block = rd.block_idx_by_text(ocr_page_text, 'NYITÓ')
        if initial_balance_text_block == -1:
            return False

        for line in ocr_page_text[initial_balance_text_block]['lines']:
            for span in line['spans']:
                text = rd.extract_span_text(span)
                if self.DUMB_BALANCE_PATTERN.match(text):
                    orig_page.add_redact_annot(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix), fill=self.REDACTION_COLOR)
                    return True

        return False


    def attempt_redacting_topmost_total_spendings(self, orig_page: pymupdf.Page, ocr_page_text, scaling_matrix: pymupdf.Matrix) -> bool:
        first_word_block = rd.block_idx_by_text(ocr_page_text, 'HALMOZOTT')
        if first_word_block == -1:
            return False

        for line in ocr_page_text[first_word_block]['lines']:
            for span in line['spans']:
                text = rd.extract_span_text(span).strip()

                if self.DUMB_BALANCE_PATTERN.match(text):
                    orig_page.add_redact_annot(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix), fill=self.REDACTION_COLOR)
                    return True

        return False


    def attempt_redacting_topmost_final_balance(self, orig_page: pymupdf.Page, ocr_page_text, scaling_matrix: pymupdf.Matrix) -> bool:
        indicator = rd.block_idx_by_text(ocr_page_text, 'HALMOZOTT')
        if indicator == -1:
            return False

        first_word_found = False
        second_word_found = False

        for block in ocr_page_text[indicator:]:
            for line in block['lines']:
                for span in line['spans']:
                    text = rd.extract_span_text(span).strip()

                    if text.startswith('Z'):
                        first_word_found = True
                    elif first_word_found and text.startswith('EG'):
                        second_word_found = True
                    elif second_word_found and self.DUMB_BALANCE_PATTERN.match(text):
                        orig_page.add_redact_annot(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix), fill=self.REDACTION_COLOR)
                        return True

        return False


    def attempt_redacting_usable_amount(self, orig_page: pymupdf.Page, ocr_page_text, scaling_matrix: pymupdf.Matrix) -> bool:
        indicator = rd.block_idx_by_text(ocr_page_text, 'FELHA')
        if indicator == -1:
            return False

        start_checking_amount = False

        for block in ocr_page_text[indicator:]:
            for line in block['lines']:
                for span in line['spans']:
                    text = rd.extract_span_text(span).strip()

                    if text.startswith('FELHA'):
                        start_checking_amount = True
                    elif start_checking_amount and self.DUMB_BALANCE_PATTERN.match(text):
                        orig_page.add_redact_annot(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix), fill=self.REDACTION_COLOR)
                        return True

        return False


    def attempt_redacting_account_number(self, orig_page: pymupdf.Page, ocr_page_text, scaling_matrix: pymupdf.Matrix) -> bool:
        indicator = rd.block_idx_by_text(ocr_page_text, 'BANKSZ')
        if indicator == -1:
            return False

        # Ha az OCR bénázik, max 3 számlaszámra hasonló szövegdarabot takarunk ki
        MAX_SPANS = 3

        start_checking = False
        stop = False
        bboxes = []

        for block in ocr_page_text[indicator:]:
            if stop:
                break
            for line in block['lines']:
                if stop:
                    break
                for span in line['spans']:
                    text = rd.extract_span_text(span).strip()

                    if not text:
                        continue
                    elif text.startswith('BANKSZ'):
                        start_checking = True
                    elif (start_checking and
                          len(bboxes) < MAX_SPANS and
                          self.DUMB_ACCOUNT_NUMBER_PATTERN.match(text)):
                        bboxes.append(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix))
                    elif start_checking and self.TEXT_START_PATTERN.match(text):
                        stop = True
                        break

        '''
        Ha az OCR nem ismeri fel egyben a számlaszámot,
        és emiatt vannak a kitakarásban rések, lehet nem lesz megfelelő
        '''
        if len(bboxes) > 0:
            x0 = min(bbox[0] for bbox in bboxes)
            y0 = min(bbox[1] for bbox in bboxes)
            x1 = max(bbox[2] for bbox in bboxes)
            y1 = max(bbox[3] for bbox in bboxes)
            orig_page.add_redact_annot((x0, y0, x1, y1), fill=self.REDACTION_COLOR)

        return len(bboxes) > 0


    def attempt_redacting_bottommost_spending(self, orig_page: pymupdf.Page, ocr_page_text, scaling_matrix: pymupdf.Matrix) -> bool:
        indicator = rd.block_idx_by_text(ocr_page_text, 'sszesen') # TODO ha talál máshol ilyet, ez eltörhet
        if indicator == -1:
            return False

        start_checking = False

        for block in ocr_page_text[indicator:]:
            for line in block['lines']:
                for span in line['spans']:
                    text = rd.extract_span_text(span).strip()

                    if not start_checking and 'sszesen' in text:
                        start_checking = True
                    elif start_checking and self.DUMB_BALANCE_PATTERN.match(text):
                        orig_page.add_redact_annot(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix), fill=self.REDACTION_COLOR)
                        return True

        return False


    def redact_spending_amounts(self, orig_page: pymupdf.Page, ocr_page_text, scaling_matrix: pymupdf.Matrix):
        # A "Terhelések" szó akár két helyen is szerepelhet egy oldalon, szóval a 'Tranzakció adatai'-tól keresünk
        indicator = rd.block_idx_by_text(ocr_page_text, 'anzakci')
        if indicator == -1:
            return

        '''
        Jobb híjján kihasználjuk azt, hogy a költések és a "Terhelések" szöveg
        ugyanott végződnek
        '''
        X1_MAX_DIST = 20
        text_span = next((span for block in ocr_page_text[indicator:]
                          for line in block['lines']
                          for span in line['spans']
                          if 'Terhel' in rd.extract_span_text(span)), None)
        text_x1 = text_span['bbox'][2] if text_span else None
        if not text_x1:
            return

        SPENDING_TEXT_Y0_MAX_DIST = 25
        spending_y0s = []

        for block in ocr_page_text[indicator:]:
            for line in block['lines']:
                for span in line['spans']:
                    text = rd.extract_span_text(span).strip()

                    if (text and text[0].isdigit() and
                        abs(text_x1 - span['bbox'][2]) < X1_MAX_DIST):
                        orig_page.add_redact_annot(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix), fill=self.REDACTION_COLOR)
                        spending_y0s.append(span['bbox'][1])

        '''
        Most kihasználva azt, hogy a tranzakciók szövegei között több hely van kihagyva,
        kitakarjuk a költések szövegét is
        '''
        prev_y = None
        spending_y0_idx = 0
        redacting = False

        keep_text = lambda text: (not text or
                                  reg.DATE_PATTERN.match(text)
                                  or self.DUMB_BALANCE_PATTERN.match(text))

        # TODO JAVITANI
        for block in ocr_page_text[indicator:]:
            for line in block['lines']:
                for span in line['spans']:
                    if spending_y0_idx >= len(spending_y0s):
                        continue

                    text = rd.extract_span_text(span).strip()
                    y0 = span['bbox'][1]
                    y1 = span['bbox'][3]

                    if not redacting and abs(spending_y0s[spending_y0_idx] - y0) < SPENDING_TEXT_Y0_MAX_DIST:
                        redacting = True
                        prev_y = y1
                        spending_y0_idx += 1

                        if not keep_text(text):
                            orig_page.add_redact_annot(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix), fill=self.REDACTION_COLOR)

                    if (redacting and
                        (abs(prev_y - y0) < SPENDING_TEXT_Y0_MAX_DIST or
                         abs(prev_y - y1) < SPENDING_TEXT_Y0_MAX_DIST)):
                        if not keep_text(text):
                            orig_page.add_redact_annot(ocr.scale_bbox_to_orig(span['bbox'], scaling_matrix), fill=self.REDACTION_COLOR)
                        prev_y = y1
                    else:
                        redacting = False


    def process_page(self, page: pymupdf.Page, page_idx: int, extracted_text) -> None:
        scaling_matrix, page_text = self.ocr_data[page_idx]
        scaling_matrix = pymupdf.Matrix(scaling_matrix) # visszaalakítjuk pymupdf Mátrixxá

        if not self.found_initial_balance:
            self.attempt_redacting_topmost_initial_balance(page, page_text, scaling_matrix)
            self.attempt_redacting_topmost_total_spendings(page, page_text, scaling_matrix)
            self.attempt_redacting_topmost_final_balance(page, page_text, scaling_matrix)
            self.attempt_redacting_usable_amount(page, page_text, scaling_matrix)

            self.found_initial_balance = True # TODO jobb név, ennek valójában maximum az első oldalon szabad futnia

        self.redact_spending_amounts(page, page_text, scaling_matrix)

        if page_idx > 0:
            self.attempt_redacting_account_number(page, page_text, scaling_matrix)
            self.attempt_redacting_bottommost_spending(page, page_text, scaling_matrix)
