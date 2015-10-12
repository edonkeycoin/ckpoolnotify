#!/bin/sh

################################################################################
#
#	File:		ckPoolNotify.sh
#
#	Contains:	This script makes sure that the network is available, then
#				calls the ckPoolNotify.py Python to send emails when 
#				stats change on the pool.
#
#	Written by:	edonkey, September 15, 2015
#
#	Donations:	18wQtEDmhur2xAd3oE8qgrZbpCDeuMsdQW
# 
################################################################################

# Parameters to the script. Change these to your specific email credentials and monitored addresses
emailUser="edonkeycoin@gmail.com"
sender="edonkeycoin@gmail.com"
recipients="edonkeycoin@gmail.com"
smtpServer="smtp.gmail.com:587"
workers="1JiWuyX94wrCr7JhkAn7x5qNMCEef1KhqX.edonkeystick"
users="1JiWuyX94wrCr7JhkAn7x5qNMCEef1KhqX"
listUrls=""
notifyTime=""

# If non-zero, then run in debug mode, outputting debug information
debug=0

# Get the full path to this script
scriptPath=`which "$0"`
scriptFullPath=`python -c "import os; print os.path.realpath('${scriptPath}')"`
scriptDir=`dirname "${scriptFullPath}"`
scriptName=`basename "${scriptFullPath}"`

# Get the path to the python script we're going to call. We assume it is in the same directory as
# this script
monitorScript="${scriptDir}/ckPoolNotify.py"
#[[ 0 -ne $debug ]] && echo "monitorScript: $monitorScript"

#-------------------------------------------------------------------------------
fatalError()
{
	echo "Fatal Error: $1"
	exit 1
}

#-------------------------------------------------------------------------------
# Borrowed from /etc/rc.common:
#
# Determine if the network is up by looking for any non-loopback
# internet network interfaces.
CheckForNetwork()
{
    local test

	if [ -z "${NETWORKUP:=}" ]; then
		test=$(ifconfig -a inet 2>/dev/null | sed -n -e '/127.0.0.1/d' -e '/0.0.0.0/d' -e '/inet/p' | wc -l)
		if [ "${test}" -gt 0 ]; then
			NETWORKUP="-YES-"
		else
			NETWORKUP="-NO-"
		fi
	fi
}

#-------------------------------------------------------------------------------
# Script starts here
#-------------------------------------------------------------------------------

CheckForNetwork
[[ 0 -ne $debug ]] && echo "NETWORKUP: $NETWORKUP"

while [ "${NETWORKUP}" != "-YES-" ]
do
        sleep 5
        NETWORKUP=
        CheckForNetwork
done

[[ 0 -ne $debug ]] && echo "The network seems to be started. Calling the monitor script..."

emailUserOption=""
if [[ ! -z "${emailUser}" ]]; then
	emailUserOption="--user ${emailUser}"
	[[ 0 -ne $debug ]] && echo "emailUserOption: $emailUserOption"
fi

# If we have workers, build up the workers option to pass to the script
workersOption=""
if [[ ! -z "${workers}" ]]; then
	workersOption="--workers ${workers}"
	[[ 0 -ne $debug ]] && echo "workersOption: $workersOption"
fi

# If we have users, build up the users option to pass to the script
usersOption=""
if [[ ! -z "${users}" ]]; then
	usersOption="--users ${users}"
	[[ 0 -ne $debug ]] && echo "usersOption: $usersOption"
fi

# If we have URLs to text file lists, build up the workers option to pass to the script
listUrlsOption=""
if [[ ! -z "${listUrls}" ]]; then
	listUrlsOption="--listurls ${listUrls}"
	[[ 0 -ne $debug ]] && echo "listUrlsOption: $listUrlsOption"
fi

# If we have a daily notification time, then add an option to pass to the script
notifyTimeOption=""
if [[ ! -z "${notifyTime}" ]]; then
	notifyTimeOption="--notifytime ${notifyTime}"
	[[ 0 -ne $debug ]] && echo "notifyTimeOption: $notifyTimeOption"
fi

# Call the script that emails me when new blocks are found
"${monitorScript}" --verbose --server $smtpServer $emailUserOption --sender $sender --recipients $recipients $workersOption $usersOption $listUrlsOption $notifyTimeOption
result=$?
if [[ $result -ne 0 ]]; then
	fatalError "Got a $result result from: ${monitorScript}"
fi

