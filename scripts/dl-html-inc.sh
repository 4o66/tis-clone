#!/bin/sh
#
# Download Body Repair Manualdocs
#

. ${HOME}/.tis/tis-clone.cfg
${SCRIPT_BASE}/confirm-login.sh

if [ x$1 = x ]; then
	echo "Syntax: $0 [WEBSITE URI PATH]"
	echo "    ie: $0 /t3Portal/external/en/bm/BM27J0U"
	exit
fi

FOLDER=$1

##
## Get Repair Manual 
##

## TOC, HTML docs and their images.  tis-fetch.py skips what is already on disk and makes about
## 3 requests per page; the wget loop below is the fallback when python3 is missing.
if command -v python3 > /dev/null 2>&1; then
	export COOKIES FSM_URLBASE WEBSITE SIID
	python3 ${SCRIPT_BASE}/tis-fetch.py "${FOLDER}"
	[ $? = 3 ] && exit 1	# session rejected; individual failed pages are listed and a rerun retries them
else
	$WG ${WEBSITE}/${FOLDER}/toc.xml
	for DOC in `grep "href=.*xhtml" ${FSM_URLBASE}/${FOLDER}/toc.xml |cut -d\" -f2`; do
		URL=`echo ${DOC} | sed -e 's/$/\?sisuffix=ff\&locale=en\&siid=1520435234586/g'`;
		$WG "${WEBSITE}/${URL}"
		mv -f ${FSM_URLBASE}/${URL} ${FSM_URLBASE}/${DOC}
	done
fi

# Create JSP static navigation
if [ -f ${FSM_URLBASE}/${FOLDER}/toc.xml ]; then
	${SCRIPT_BASE}/toc2html ${FSM_URLBASE}/${FOLDER}/toc.xml > ${FSM_URLBASE}/${FOLDER}/toc.html
	cp ${BASE}/website-framework/index.html  ${FSM_URLBASE}/${FOLDER}/
fi

