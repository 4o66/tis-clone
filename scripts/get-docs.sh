#!/bin/sh
#
# Download standalone documents (bulletins, collision repair bulletins, campaigns, accessory and
# training guides) by type and ID.  IDs come from the library search results on the TIS site: each
# result link's objType= is the type and its href=<type>/<ID>/... gives the ID.
#
#   get-docs.sh sb-usa-tdm:T-SB-0012-21 sb:T-BO005-92 crib:T-CRIB-201-D
#
# Saves to $DOWNLOAD_TO/docs/<type>/<ID>.pdf.  See scripts/tis-docs.py for the list of types.
#

. ${HOME}/.tis/tis-clone.cfg

if [ x$1 = x ]; then
	echo "Syntax: $0 TYPE:ID [TYPE:ID ...]"
	echo "    ie: $0 sb-usa-tdm:T-SB-0012-21 crib:T-CRIB-201-D"
	exit 1
fi

${SCRIPT_BASE}/confirm-login.sh || exit 1
export COOKIES DOWNLOAD_TO WEBSITE SIID
python3 ${SCRIPT_BASE}/tis-docs.py "$@"
