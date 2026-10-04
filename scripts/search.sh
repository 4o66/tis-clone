#!/bin/sh
#
# Find everything TIS has for a vehicle and optionally download it all.  Run from anywhere.
#
#   search.sh --model "Prius Prime" --year 2019             # list the manuals and documents
#   search.sh --model "Prius Prime" --year 2019 --download  # and fetch them
#   search.sh --vin JTDxxxxxxxxxxxxxx --download            # model and year from the VIN
#   search.sh --list-models                                 # valid --model values
#
# Then continue with HOWTO step 5 (dl-framework.sh) onward.
#

. ${HOME}/.tis/tis-clone.cfg

# No confirm-login.sh here: tis-search.py detects a rejected session itself, and it saves rotated
# cookies back to cookies.txt, which wget-based scripts don't.
mkdir -p ${DOWNLOAD_TO}
export COOKIES DOWNLOAD_TO WEBSITE SCRIPT_BASE FSM_URLBASE SIID
python3 ${SCRIPT_BASE}/tis-search.py "$@"
