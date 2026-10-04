#!/bin/sh
#
# Renew an expired TIS portal session without a new password or verification code.
#
# tis-login.sh saves two kinds of cookie: the portal session (T3SESSIONID) and the sign-on token
# (iPlanetDirectoryPro).  The portal session can lapse or be rejected long before the sign-on token
# does; while the token is still valid, the portal will issue a new session from it.  If the token
# itself has ended (for example a login in a browser ended it), this fails and tis-login.sh is needed.
#
# Never prints cookie values.  The old cookies.txt is kept as cookies.txt.prev.
#

. ${HOME}/.tis/tis-clone.cfg

UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:57.0) Gecko/20100101 Firefox/57.0"
T=`mktemp -d ${TISTMPDIR}/tis-renew.XXXXXX`
trap 'rm -rf $T' EXIT

[ -f ${COOKIES} ] || { echo "No ${COOKIES}.  Run ${SCRIPT_BASE}/tis-login.sh first."; exit 1; }
grep -q iPlanetDirectoryPro ${COOKIES} || { echo "No sign-on token in ${COOKIES}.  Run ${SCRIPT_BASE}/tis-login.sh."; exit 1; }

# Drop the old portal session and ask for a new one with the sign-on token
grep -vE 'T3SESSIONID|_WL_AUTHCOOKIE' ${COOKIES} > $T/cookies.txt
curl -s -o $T/portal.html -L -A "$UA" -c $T/cookies.txt -b $T/cookies.txt \
	-H "Referer: ${WEBSITE}/" "${WEBSITE}/t3Portal/login"

if ! grep -q T3SESSIONID $T/cookies.txt; then
	echo "The sign-on token has ended.  Run ${SCRIPT_BASE}/tis-login.sh."
	exit 1
fi

cp ${COOKIES} ${COOKIES}.prev
cp $T/cookies.txt ${COOKIES}
if ${SCRIPT_BASE}/confirm-login.sh > /dev/null; then
	echo "Session renewed."
else
	cp ${COOKIES}.prev ${COOKIES}
	echo "The portal issued a session but it does not work.  Run ${SCRIPT_BASE}/tis-login.sh."
	exit 1
fi
