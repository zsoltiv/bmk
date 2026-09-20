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
from typing import Any

import pymupdf

type Word = tuple[float, float, float, float, str, Any, Any, Any]

def extract_span_text(span: dict[str, Any]) -> str:
    return ''.join(char['c'] for char in span['chars'])

def compute_substring_bounding_box(span_chars: list[dict[str, Any]]) -> tuple[float, float, float, float]:
    x0: float = min(c['bbox'][0] for c in span_chars)
    y0: float = min(c['bbox'][1] for c in span_chars)
    x1: float = max(c['bbox'][2] for c in span_chars)
    y1: float = max(c['bbox'][3] for c in span_chars)

    return (x0, y0, x1, y1)

def block_idx_by_text(page_text: list[dict[str, Any]], substr: str) -> int:
    return next(
        (i for i, e in enumerate(page_text) if any(
            substr in extract_span_text(span)
            for line in e['lines']
            for span in line['spans'])
        ), -1
    )

def line_idx_by_text(block: dict[str, Any], substr: str) -> int:
    return next(
        (i for i, line in enumerate(block['lines']) if any(
            substr in extract_span_text(span)
            for span in line['spans']
        )), -1
    )


def block_idx_by_regex(page_text: list[dict[str, Any]], regex: re.Pattern) -> int:
    return next(
        (i for i, e in enumerate(page_text) if any(
            regex.search(extract_span_text(span))
            for line in e['lines']
            for span in line['spans'])
        ), -1
    )

def find_numbers_next_to_text(
    page: pymupdf.Page,
    label_text: str,
    page_text: list[Word],
    regex: re.Pattern[str] | None = None
) -> list[Word] | None:
    """Function returns with a list of words within the same line of the provided text or None if there cannot be found any.
    Also supports a positional argument called regex to apply to the contents of such words, if none is provided it defaults
    to returning all that can be found within the same line.

    Note: Important caveat is that the returned list cannot be empty,
    it will either be a list with at least a single element, or None."""

    label_rects = page.search_for(label_text)
    if not label_rects:
        return None

    label_rect = label_rects[0]
    y_min = label_rect.y0 - 2
    y_max = label_rect.y1 + 2
    x_start = label_rect.x1


    words_in_line: list = []

    for word in page_text:
        w_x0, w_y0, _, w_y1, _ = word[:5]
        w_y_center: float = float(w_y0 + w_y1) / 2.0

        if (y_min <= w_y_center <= y_max) and (w_x0 >= x_start):
            words_in_line.append(word[:5])

    if not words_in_line:
        return None

    words_in_line = sorted(words_in_line, key=lambda w: w[0])

    if regex is None:
        return words_in_line if words_in_line else None
    else:
        fitting_words_in_line = [
            word_data for word_data in words_in_line
            if re.match(regex, word_data[4])
        ]

        return fitting_words_in_line if fitting_words_in_line else None
