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

from os import PathLike
from typing import Any

import cv2 as cv
import pymupdf
from cv2.typing import MatLike
from numpy import ndarray, uint8


def scale_bbox_to_orig(bbox, scaling_matrix: pymupdf.Matrix) -> pymupdf.Rect:
    return pymupdf.Rect(bbox) * scaling_matrix


def preprocess_scanned_page(
    scanned: pymupdf.Page,
    dpi: int = 300,
    denoise_h: int = 20,
    threshold_value: int = 190
) -> tuple[pymupdf.Matrix, pymupdf.Document]:
    '''
    Szkennelt dokumentumot zajmentesít és OCR-t futtat rajta.
    A végeredmény az oldal magasságának, szélességének skálázása,
    és egy 1 oldalas dokumentum
    '''
    pixmap: pymupdf.Pixmap = scanned.get_pixmap(dpi=dpi)
    img: ndarray = ndarray(
        shape=(pixmap.h, pixmap.w, pixmap.n),
        dtype=uint8,
        buffer=pixmap.samples,
        strides=(pixmap.stride, pixmap.n, 1)
    )

    gray: MatLike  = cv.cvtColor(img, cv.COLOR_RGB2GRAY)
    denoised: MatLike = cv.fastNlMeansDenoising(gray, h=denoise_h)
    thresh: MatLike = cv.threshold(denoised, threshold_value, 255, cv.THRESH_BINARY)[1]
    rgb: MatLike = cv.cvtColor(thresh, cv.COLOR_GRAY2RGB) # mupdf RGB-t vár el

    preprocessed_pixmap: pymupdf.Pixmap = pymupdf.Pixmap(pymupdf.csRGB, rgb.shape[1], rgb.shape[0], rgb.tobytes(), False)

    new_doc: pymupdf.Document = pymupdf.open('pdf', preprocessed_pixmap.pdfocr_tobytes(language='hun'))
    # shoutout to A2 lineáris leképezések
    scaling_matrix: pymupdf.Matrix = new_doc[0].rect.torect(scanned.rect)

    return scaling_matrix, new_doc


def process_worker(
    filename: str | PathLike,
    pagenum: int,
    dpi: int,
    h: int,
    threshold: int
) -> tuple[tuple[float, float, float, float, float, float], list[dict[str, Any]]]:

    doc: pymupdf.Document
    sm: Any
    scanned_doc: Any
    page_text: dict[str, Any]
    filtered_blocks: list[dict[str, Any]]
    pickleable_matrix: tuple[float, float, float, float, float, float]

    with pymupdf.open(filename) as doc:
        sm, scanned_doc = preprocess_scanned_page(doc[pagenum], dpi, h, threshold)
        page_text = scanned_doc[0].get_text(option='rawdict')
        filtered_blocks = [b for b in page_text['blocks'] if b['type'] == 0]
        # Python tuple-t tudunk folyamatok között küldeni
        pickleable_matrix = (sm.a, sm.b, sm.c, sm.d, sm.e, sm.f)
        return pickleable_matrix, filtered_blocks
