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

import argparse
from pathlib import Path
from sys import exit, stderr

import pymupdf

from .otp_redactor import OtpRedactor
from .redactor import Redactor
from .unicredit_redactor import UnicreditRedactor

ALL_REDACTORS: dict[str, type[Redactor]] = {
    'unicredit': UnicreditRedactor,
    'otp': OtpRedactor,
}

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='mueper-redactor',
        description='Bankszámlakivonatok kitakarása egyetemi bürokráciához'
    )
    parser.add_argument('input_pdf')
    parser.add_argument(
            'redactor',
            choices=ALL_REDACTORS.keys(),
            type=str.lower,
            help="A számlakivonat típusa (pl. otp, unicredit)")
    parser.add_argument('output_pdf')
    args = parser.parse_args()

    input_path = Path(args.input_pdf)
    if not input_path.is_file():
        print(f'Hiba: A fájl nem található - {args.input_pdf}', file=stderr)
        exit(1)

    output_path = Path(args.output_pdf)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        doc = pymupdf.open(input_path)
    except Exception as e:  # noqa: BLE001 <- nem szereti a type checkerem hogy blanket exception-t catchelünk, ezzel kikapcsolom
        print(f'Hiba a PDF megnyitásakor (hibás fájl?): {e}', file=stderr)
        exit(1)

    redactor_class = ALL_REDACTORS[args.redactor]
    with redactor_class(doc, args.output_pdf) as redactor:
        redactor.process_pages()

if __name__ == '__main__':
    main()
