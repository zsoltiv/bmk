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

GENERIC_SPENDING_PATTERN: re.Pattern[str] = re.compile(r'\-[0-9]{1,3}(?:\.[0-9]{3})*,\d{2}') #-YYYY-MM-DD
DATE_PATTERN: re.Pattern[str] = re.compile(r'[0-9]{4}\.[0-9]{2}\.[0-9]{2}') # maybe deprecate and get rid of? why redact dates?
MONTH_DAY_PATTERN: re.Pattern[str] = re.compile(r'[0-9]{2}\/[0-9]{2}') # same with the normal date pattern

#-YYYY-MM-DD with positive lookforward applied to -, the negative sign is ignored but is required
ERSTE_SPENDING_PATTERN: re.Pattern[str] = re.compile(r'^(-)?(\d+(?:\.\d+)?(?:,\d+)?)$')
