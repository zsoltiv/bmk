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
from .utils.rawdict import Word, find_numbers_next_to_text
from .utils.regex import ERSTE_SPENDING_PATTERN


class ErsteRedactor(Redactor):
    def __init__(self, doc: pymupdf.Document, output_filename: str, extract_kind: TextExtractKind = TextExtractKind.WORDS) -> None:
        super().__init__(doc, output_filename, extract_kind)

        self.redacted_initial_balance: bool = False

        self.prev_tx_was_negative: bool = False # tx = transaction
        self.saved_col_x_min: float | None = None
        self.saved_col_x_max: float | None = None
        self.saved_header_x0: float | None = None

    def redact_account_number(self, page: pymupdf.Page) -> None:
        labels_to_redact = [
            'Bankszámla típusa',
            'Bankszámlaszám',
            'Nemzetközi bankszámlasz. (IBAN)',
            'Ügyfélazonosító'
        ]

        for label in labels_to_redact:
            label_rects = page.search_for(label)

            for rect in label_rects:
                avg_char_width = rect.width / len(label)
                max_redact_width = avg_char_width * 40
                end_x = min(rect.x1 + 5 + max_redact_width, page.rect.width)

                bbox = pymupdf.Rect(rect.x1 + 5, rect.y0, end_x, rect.y1)
                page.add_redact_annot(bbox, fill=self.REDACTION_COLOR)

    def redact_opening_balance(self, page: pymupdf.Page, page_text: list[Word]) -> None:
        opening_rects = page.search_for("Nyitó egyenleg")
        balance_rects = page.search_for("Egyenleg")

        if not opening_rects or not balance_rects:
            return

        opening_rect = opening_rects[0]
        balance_rect = balance_rects[0]

        col_x_min = balance_rect.x0 - 20
        col_x_max = balance_rect.x1 + 30
        y_search_top = opening_rect.y1
        y_search_bottom = opening_rect.y1 + 30



        for word in page_text:
            w_x0, w_y0, _, w_y1, text = word[:5]
            w_y_center: float = float(w_y0 + w_y1) / 2.0

            in_same_column: bool = (col_x_min <= w_x0 <= col_x_max)
            in_same_row: bool = (y_search_top <= w_y_center <= y_search_bottom)

            if in_same_column and in_same_row and re.match(ERSTE_SPENDING_PATTERN, text):
                    page.add_redact_annot(pymupdf.Rect(word[:4]), fill=self.REDACTION_COLOR)
                    break

    def redact_balances(self, page: pymupdf.Page, page_text: list[Word]) -> None:
        column_rules = {
            "Összeg(+/-)": "negative_only",
            "Egyenleg": "all",
            "Illeték (HUF)": "illetek",
            "Zárolt összeg": "all"
        }

        columns = []
        for header, rule in column_rules.items():
            rects = page.search_for(header)
            if rects:
                header_rect = rects[0]
                x_min = header_rect.x0 - 30
                x_max = header_rect.x1 + 30
                y_min = header_rect.y1
                columns.append((x_min, x_max, y_min, rule))

        for word in page_text:
            w_x0, w_y0, w_x1, w_y1, text = word[:5]

            matched_rule = None
            for (col_x_min, col_x_max, col_y_min, rule) in columns:
                if col_x_min < w_x0 and w_x1 < col_x_max and w_y0 >= col_y_min:
                    matched_rule = rule
                    break

            if matched_rule:
                word_bbox = pymupdf.Rect(w_x0, w_y0, w_x1, w_y1)

                if matched_rule == "illetek":
                    if not re.search(r'[A-Za-z]', text):
                        page.add_redact_annot(word_bbox, fill=self.REDACTION_COLOR)
                    continue

                match = re.match(ERSTE_SPENDING_PATTERN, text)
                if match:
                    has_minus = bool(match.group(1))

                    if matched_rule == "negative_only" and not has_minus:
                        continue

                    number_only = match.group(2)
                    number_rects = page.search_for(number_only, clip=word_bbox)
                    for rect in number_rects:
                        page.add_redact_annot(rect, fill=self.REDACTION_COLOR)

    def redact_reference_data_if_negative(self, page: pymupdf.Page, page_text: list[Word]) -> None:
        prev_is_neg = self.prev_tx_was_negative
        amount_rects = page.search_for("Összeg(+/-)")

        if amount_rects:
            amount_header = amount_rects[0]
            col_x_min = amount_header.x0 - 40
            col_x_max = amount_header.x1 + 40
            header_y = amount_header.y1

            self.saved_col_x_min = col_x_min
            self.saved_col_x_max = col_x_max
            self.saved_header_x0 = amount_header.x0
        else:
            col_x_min = self.saved_col_x_min
            col_x_max = self.saved_col_x_max
            header_y = 0
            # Ha nincs mentett oszlop adat, megszakítjuk a keresést
            if col_x_min is None or col_x_max is None:
                return

        # Biztonságos értékadás a szellemblokkoknak (Type-safe fallback)
        safe_header_x0 = self.saved_header_x0 if self.saved_header_x0 is not None else (col_x_max - 40)
        ghost_right_limit = safe_header_x0 - 5

        transactions = []

        for word in page_text:
            w_x0, w_y0, w_x1, w_y1, text = word[:5]
            if float(w_x0) >= col_x_min and float(w_x1) <= col_x_max and float(w_y0) >= header_y:
                match = re.match(ERSTE_SPENDING_PATTERN, text)
                if match:
                    transactions.append({
                        'y0': w_y0,
                        'amount_x0': w_x0,
                        'is_neg': bool(match.group(1))
                    })

        transactions = sorted(transactions, key=lambda t: t['y0'])

        blocks = []
        if transactions:
            blocks.append({
                'y_top': 0,
                'y_bottom': transactions[0]['y0'] - 4,
                'is_neg': prev_is_neg,
                'amount_x0': ghost_right_limit
            })
            for i in range(len(transactions)):
                y_top = transactions[i]['y0'] - 4
                y_bottom = page.rect.height if i == len(transactions) - 1 else transactions[i+1]['y0'] - 4
                blocks.append({
                    'y_top': y_top,
                    'y_bottom': y_bottom,
                    'is_neg': transactions[i]['is_neg'],
                    'amount_x0': transactions[i]['amount_x0'] - 5
                })
            self.prev_tx_was_negative = transactions[-1]['is_neg']
        else:
            blocks.append({
                'y_top': 0,
                'y_bottom': page.rect.height,
                'is_neg': prev_is_neg,
                'amount_x0': ghost_right_limit
            })

        target_labels = [
                "IBAN szám:", "Partner számlatulajdonos:", "Tranzakció azonosító:",
                "Tranzakció idopontja:", "Átutalás azonosító:", "Kártyaszám - Tr.időpont",
                "Terminál - eng.kód Trtip", "Elfogadó", "Kártyabirt", "Kártyabirtokos neve:",
                "HITELEZÉSSEL KAPCS. TERHELÉS:", "megjegyzés:", "Bankszámla száma:",
                "Partner számla tulajdonos:", "Bizonylatszám:", "Közlemény:", "Tr. azonosító:"
            ]

        for label in target_labels:
            raw_rects = page.search_for(label)
            merged_rects = []

            for r in raw_rects:
                r_y_center = (r.y0 + r.y1) / 2.0
                found_group = False
                for m in merged_rects:
                    m_y_center = (m.y0 + m.y1) / 2.0
                    if abs(r_y_center - m_y_center) < 5:
                        m.x0 = min(m.x0, r.x0)
                        m.y0 = min(m.y0, r.y0)
                        m.x1 = max(m.x1, r.x1)
                        m.y1 = max(m.y1, r.y1)
                        found_group = True
                        break

                if not found_group:
                    merged_rects.append(pymupdf.Rect(r))

            for rect in merged_rects:
                label_y_center = (rect.y0 + rect.y1) / 2.0
                parent_block = next((b for b in blocks if b['y_top'] <= label_y_center <= b['y_bottom']), None)

                if parent_block and parent_block['is_neg']:
                    max_x: float = -1.0
                    for word in page_text:
                        w_x0, w_y0, w_x1, w_y1 = word[:4]
                        w_y_center = float(w_y0 + w_y1) / 2.0

                        if ((rect.y0 - 2 <= w_y_center <= rect.y1 + 2) and \
                           (w_x0 >= rect.x1) and \
                           (w_x1 <= parent_block['amount_x0'])) and float(w_x1) > max_x:
                                max_x = float(w_x1)

                    if max_x != -1.0:
                        redact_area = pymupdf.Rect(rect.x1 + 3, rect.y0 - 2, max_x + 3, rect.y1 + 2)
                        page.add_redact_annot(redact_area, fill=self.REDACTION_COLOR)

    def redact_misc_numbers(self, page: pymupdf.Page, page_text: list[Word]) -> None:
        labels_for_numbers_accounted_for = [
            "Záró egyenleg", "Összes terhelés", "LAKOSSÁGI FOLYÓSZÁMLAHITEL",
            "Összesen", "Felhasználható egyenleg"
        ]

        for label in labels_for_numbers_accounted_for:
            words = find_numbers_next_to_text(page, label, page_text, regex=ERSTE_SPENDING_PATTERN)
            if not words:
                continue

            for word in words:
                redact_area = pymupdf.Rect(word[:4])
                page.add_redact_annot(redact_area, fill=self.REDACTION_COLOR)

    def redact_pending_card_transactions(self, page: pymupdf.Page, page_text: list[Word]) -> None:
        info_rects = page.search_for("Részletező információk")
        amount_rects = page.search_for("Zárolt összeg")

        if not info_rects or not amount_rects:
            return

        info_header = info_rects[0]
        amount_header = amount_rects[0]

        col_x_min = info_header.x0 - 5
        col_x_max = amount_header.x0 - 15
        y_top = info_header.y1
        y_bottom = page.rect.height

        summary_rects = page.search_for("Zárolt összegek összesen")
        if summary_rects:
            y_bottom = summary_rects[0].y0 - 5



        for word in page_text:
            w_x0, w_y0, w_x1, w_y1 = word[:4]
            w_x_center = float(w_x0 + w_x1) / 2.0
            w_y_center = float(w_y0 + w_y1) / 2.0

            if (col_x_min <= w_x_center <= col_x_max) and (y_top <= w_y_center <= y_bottom):
                page.add_redact_annot(pymupdf.Rect(word[:4]), fill=self.REDACTION_COLOR)

    def redact_technical_artifacts(self, page: pymupdf.Page, page_text: list[Word]) -> None:
        """Eltávolítja a margókon lévő technikai AFP metaadatokat."""
        for word in page_text:
            w_x0, _, _, _, text = word[:5]
            artifact_found: bool = ".afp" in text.lower() or ("_" in text and len(text) > 20 and any(char.isdigit() for char in text))
            artifact_close_to_margin: bool = float(w_x0) < 50.0 or w_x0 > page.rect.width - 150
            if artifact_found and artifact_close_to_margin:
                page.add_redact_annot(pymupdf.Rect(word[:4]), fill=self.REDACTION_COLOR)



    def process_page(self, page: pymupdf.Page, page_idx: int, extracted_text: list[Word]) -> None:
        self.redact_account_number(page)
        self.redact_opening_balance(page, extracted_text)
        self.redact_balances(page, extracted_text)
        self.redact_reference_data_if_negative(page, extracted_text)
        self.redact_misc_numbers(page, extracted_text)
        self.redact_pending_card_transactions(page, extracted_text)
        self.redact_technical_artifacts(page, extracted_text)
