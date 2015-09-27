#!/usr/bin/env python -u

"""Script used to monitor the CK Solo bitcoin mining pool."""

################################################################################
#
#	File:		ckPoolNotify.py
#
#	Contains:	This script monitors the CK Solo pool, emailing the caller 
#				with status changes.
#
#				Currently this script only monitors changes to the best shares
#				submitted by the specified workers or users. An email will
#				be sent if any monitored best share improves.
#
#				See the help documentation for details on using this script:
#
#				ckPoolNotify.py --help
#
#	Written by:	edonkey, September 15, 2015
#
#	Donations:	18wQtEDmhur2xAd3oE8qgrZbpCDeuMsdQW
# 
################################################################################

import os
import sys
import signal
import time
import datetime
import urlparse
import json
import requests
import keyring
import smtplib
import email
import pickle
import getpass
from email.MIMEMultipart import MIMEMultipart
from email.mime.text import MIMEText
from os.path import expanduser

from optparse import OptionParser

# Globals
gDebug = False
gVerbose = False
gQuiet = False

gSeparator = "----------------------------------------------------------------------------------------------------"

# Globals used to test the block finding code. Should be left off unless you're developing or 
# testing this script
gDebugPretendWeFoundABlock = False
gDebugFakeFoundAddress = None

# This system name will appear in the platform keyring.
gKeyringSystem = "ckPoolNotify"

# Defaults
gDefaultPoolUrl = "http://solo.ckpool.org"
gDefaultCkSoloPoolFeeAddress = "1PKN98VN2z5gwSGZvGKS2bj8aADZBkyhkZ"

# Number of minutes between checks to see if a block was found
gDefaultBlockCheckMinutes = 5

gDefaultDifficultyUrl = "https://blockexplorer.com/q/getdifficulty"
gDefaultDifficultyJsonKey = "difficulty"

gDefaultSmptServer = "smtp.gmail.com:587"

gDefaultMonitorSleepSeconds = 90

gDefaultDateTimeStrFormat = "%Y-%m-%d %H:%M:%S"

# Boolean expression dictionary
gBooleanExpressionDict = {
	"on":		True,
	"off":		False,
	"true":		True,
	"false":	False,
	"yes":		True,
	"no":		False,
	"1":		True,
	"0":		False,
}

# Get the name and path to our script
gScriptPathArg = sys.argv[0]
gScriptName	 = os.path.basename(gScriptPathArg)

# Get the user's home directory
gHomeDir = expanduser("~")

# Define the file where we'll store the current stats dictionary. We do this conditionally
# based on the platform. For all platforms other than Windows, we use the dot char prefix to make
# the file invisible.
# TODO: For windows, consider setting the file to be invisible.
if sys.platform == "win32":
	gSavedStatsFilePath = os.path.join(gHomeDir, "ckPoolNotify_SavedStats")
else:
	gSavedStatsFilePath = os.path.join(gHomeDir, ".ckPoolNotify_SavedStats")

#---------------------------------------------------------------------------------------------------
def stringArgCheck(arg):
	return (arg		!= None)	and \
		   (len(arg) > 0   )	and \
		   (arg		!= "")		and \
		   (arg		!= '')		and \
		   (arg		!= "\"\"")

#---------------------------------------------------------------------------------------------------
def exitFail(message="", exitCode=1):
	if stringArgCheck(message):
		sys.stderr.write(message + "\n")
	sys.exit(exitCode)

#---------------------------------------------------------------------------------------------------
def signalHandler(signal, frame):
  print('')
  print('Exiting...')
  sys.exit(0)

#---------------------------------------------------------------------------------------------------
# Get the current date/time in the specified format
def getNowStr(format=gDefaultDateTimeStrFormat):
	return datetime.datetime.now().strftime(format)

#---------------------------------------------------------------------------------------------------
# Print the specified strings, prepending with the current date/time
def p(*args):
	line = getNowStr() + ": ";
	for arg in args:
		line = " ".join([line, str(arg)])
	print line
	return

#---------------------------------------------------------------------------------------------------
# Evaluate the specified boolean expression string into a boolean value. Also returns whether or
# not a valid, known boolean expression string was provided
def evaluateBoolExpression(boolExpression):
	expressionValue = False
	validExpression = False
	
	boolExpressionLower = boolExpression.lower()
	if boolExpressionLower in gBooleanExpressionDict:
		validExpression = True
		expressionValue = gBooleanExpressionDict[boolExpressionLower]
	
	return (expressionValue, validExpression)

#---------------------------------------------------------------------------------------------------
# Build up a list of valid expressions dynamically from the dictionary
def getValidBoolExpresionsStr():
	validExpressions = ""
	for key in gBooleanExpressionDict:
		if len(validExpressions) > 0:
			validExpressions += ", "
		validExpressions = validExpressions + key
	
	return validExpressions

#---------------------------------------------------------------------------------------------------
def exitFailBadBooleanExpression(message, badExpression):
	errorMessage = message + ": \"" + badExpression + "\". Valid boolean expressions include: " + getValidBoolExpresionsStr()
	exitFail(errorMessage)

#---------------------------------------------------------------------------------------------------
def setPassword(user, password):
	if not stringArgCheck(password):
		exitFail("You have to specify an actual password.")
	
	# Save the password in the keychain
	if gDebug: print("Saving the password to the keychain under this sender: \"" + user + "\"")
	keyring.set_password(gKeyringSystem, user, password)

#---------------------------------------------------------------------------------------------------
def setOrGetPassword(user, passwordSpecified):
	# If a password was specified, then use it. Otherwise get the password out of the keychain.
	password = ""
	if passwordSpecified:
		password = passwordSpecified
		setPassword(user, password)
	else:
		password = keyring.get_password(gKeyringSystem, user)
		if not stringArgCheck(password):
			print("No password found in the keychain for this sender: \"" + user + "\"")
			exitFail("You must specify a password at least once in order to store it in the keychain for this user.")
	
	return password

#---------------------------------------------------------------------------------------------------
def getCurrentDifficulty(getDifficultyUrl=gDefaultDifficultyUrl, difficultyKey=gDefaultDifficultyJsonKey):
	# Default the difficulty to zero (yeah, you wish!) in case we fail to get it from the web
	curDifficulty = 0.0
	
	try:
		if gDebug: print("Attempting to get the current difficulty from this URL: \"" + getDifficultyUrl + "\", and this key: " + difficultyKey)
		
		# Get the JSON result from the difficulty provider URL
		r = requests.get(getDifficultyUrl)
		status = r.status_code
		r.raise_for_status()
		data = r.json()
		if gDebug: print("  JSON returned: " + str(data))
		
		# Get the difficulty value from the JSON data retrned
		curDifficulty = data[difficultyKey]
		if gDebug: print("  curDifficulty: " + str(curDifficulty))
	except requests.exceptions.ConnectionError, e:
		print('Could not get difficulty due to a connection Error.')
	except Exception, e:
		print('Fetching data failed: %s' % str(e))
	
	return curDifficulty

#---------------------------------------------------------------------------------------------------
def wasABlockFound(lastBlock, poolFeeAddress=gDefaultCkSoloPoolFeeAddress):
	# Initialize the return values
	newBlock = 0
	blockFinderAddress = ""

	# Assemble the pool fee address URL. If there's a new input to this address, it means
	# the pool found a block. Also, the other input will be the block finder's address.
	poolFeeAddressUrl = "https://blockchain.info/address/" + poolFeeAddress + "?format=json"

	try:
		if gDebug: print("Looking for a payout to the pool fee address: \"" + poolFeeAddress + "\"")
		response = requests.get(poolFeeAddressUrl)
		data = response.json()
		blockNumberFound = data['txs'][0][u'block_height']
		
		if gDebug:
			print("  Found this block number: " + str(blockNumberFound))

		# HACK TEST to fake out a found block.
		if gDebugPretendWeFoundABlock:
			print ("  Pretend we found a block by hacking the last block number.")
			lastBlock = blockNumberFound - 1
	
		# Check to see if this is a new block
		if blockNumberFound > lastBlock:
			newBlock = blockNumberFound
			blockFinderAddress = data['txs'][0][u'out'][0][u'addr']
			if gDebug:
				print("  And this block finder: " + blockFinderAddress)
		elif gDebug:
			print("    This is not a new block. Bummer...")
	except requests.exceptions.ConnectionError, e:
		p("Connection Error. Will retry later.." )
		status = -2
	except Exception, e:
		p("Fetching data failed: %s" % str(e))
		status = -2
	
	return (newBlock, blockFinderAddress)

#---------------------------------------------------------------------------------------------------
class EmailServer:

	#---------------------------------------------------------------------------
	# Default constructor
	def __init__(self, serverUrl, user, password):
		# Initialize the member variables with defaults
		self.serverUrl = serverUrl
		self.user = user		
		self.password = password

	#---------------------------------------------------------------------------
	def send(self, sender, recipients, subject, body, printEmail=False):
		didSend = False
	
		recipientList = recipients if type(recipients) is list else [recipients]
		
		# If running in verbose mode or if the caller wants us to print the email,
		# then print it out now
		if gVerbose or printEmail:
			print(gSeparator)
			p("Sending an email:")
			print("  Sender:  " +  sender)
			print("  Recipients:  " +  str(recipients))
			print("  Subject:  " +  subject)
			print("  Body:\n\n" +  body)
			print(gSeparator)
			print("")
	
		# Prepare actual message
		message = email.MIMEMultipart.MIMEMultipart()
		message['From'] = sender
		message['To'] = email.Utils.COMMASPACE.join(recipientList)
		message['Subject'] = subject  
		message.attach(MIMEText(body, 'plain'))
	
		try:
			smtp = smtplib.SMTP(self.serverUrl)
			smtp.ehlo()

			# If a user and password were specified, then perform authentication
			if stringArgCheck(self.user) and stringArgCheck(self.password):
				smtp.starttls()
				smtp.login(self.user, self.password)

			# Send the email
			smtp.sendmail(sender, recipientList, message.as_string())

			# Shut down the server
			smtp.quit()
		
			# Remember that we succeeded
			didSend = True
		except Exception, err:
			print "Failed to send mail:", err
	
		return didSend

#---------------------------------------------------------------------------------------------------
# This class saves status information for user and worker URLs to a file. The file is actually
# a pickled dictionary where the key is the status URL and the value is the JSON dictionary 
# returned from the pool API. 
#
# Rather than just storing the bestshare (as a previous iteration of this script did), storing the
# entire JSON dictionary for monitored URLs should allow us to add new monitoring features without
# changing the file format of the stats data.
class SavedStats:

	#---------------------------------------------------------------------------
	# Default constructor
	def __init__(self, path):
		# Initialize the member variables with defaults
		self.path = path
		self.statsDict = None
		self.lastBlock = 0
		self.restore()

		# If we didn't restore a stats dictionary, then instance a new one
		if not self.statsDict:
			if gDebug: print("Couldn't find saved stats data. Initializing a new dictionary...")
			self.statsDict = {}

	#---------------------------------------------------------------------------
	def restore(self):
		if os.path.exists(self.path) and (0 != os.path.getsize(self.path)):
			if gDebug: print("Reading the saved saved stats dictionary from here: " + self.path)
			try:
				file = open(self.path, "rb")
				file.seek(0, 0)
				unpickled = pickle.load(file)
				self.statsDict = unpickled["userStats"]
				if "lastBlock" in unpickled:
					self.lastBlock = unpickled["lastBlock"]
				file.close()
				if gDebug: print("  Restored these stats key/values:" + str(self.statsDict))
			except Exception, err:
				print "Exception trying to access the saved saved stats data file:", err

	#---------------------------------------------------------------------------
	def save(self):
		if gDebug: print("Writing the saved saved stats dictionary from here: " + self.path)
		try:
			file = open(self.path, "a+b")
			file.seek(0, 0)
			file.truncate()
			dictToPickle = {"userStats": self.statsDict, "lastBlock": self.lastBlock}
			pickle.dump(dictToPickle, file)
			file.close()
		except Exception, err:
			print "Exception trying to save the saved stats data file:", err

#---------------------------------------------------------------------------------------------------
def getLastUpdateTimeFromStatsJson(statsJson, localTime=False):
	# Set default values in case we can't find a given hash rate in the stats
	lastUpdateTime = None

	try:
		lastUpdateSecs = statsJson['lastupdate']
		if localTime:
			lastUpdateTime = time.localtime(lastUpdateSecs)
		else:
			lastUpdateTime = time.gmtime(lastUpdateSecs)
	except Exception, e:
		errorStr = "Fetching data failed: " + str(e)
		p(errorStr)

	return lastUpdateTime

#---------------------------------------------------------------------------------------------------
def getHashRatesFromStatsJson(statsJson):
	# Set default values in case we can't find a given hash rate in the stats
	hashRate5m = "?"
	hashRate1hr = "?"
	hashRate1d = "?"
	hashRate7d = "?"
	
	# Get last hash rates out of the specified JSON
	try:
		hashRate5m = statsJson['hashrate5m']
	except Exception, e:
		errorStr = "Fetching data failed: " + str(e)
		p(errorStr)

	try:
		hashRate1hr = statsJson['hashrate1hr']
	except Exception, e:
		errorStr = "Fetching data failed: " + str(e)
		p(errorStr)

	try:
		hashRate1d = statsJson['hashrate1d']
	except Exception, e:
		errorStr = "Fetching data failed: " + str(e)
		p(errorStr)

	try:
		hashRate7d = statsJson['hashrate7d']
	except Exception, e:
		errorStr = "Fetching data failed: " + str(e)
		p(errorStr)
	
	return (hashRate5m, hashRate1hr, hashRate1d, hashRate7d)


#---------------------------------------------------------------------------------------------------
def getUserAndWorkersFromURLs(listUrls):
	listedUsers = []
	listedWorkers = []
	
	for curListUrl in listUrls:
		try:
			if gDebug: print("Attempting to get the user/workers list from this URL: \"" + curListUrl + "\"")
		
			# Get the text result from the list URL
			r = requests.get(curListUrl)
			listText = r.text
			if gDebug: print("  Text returned: " + listText)
	
			# Split the text into lines, then evaluate each one. Attempts to deal with
			# URLs as well as simple addresses
			listLines = listText.splitlines()
			for curListLine in listLines:
				curLine = curListLine.strip()
				if stringArgCheck(curLine):
					# Ignore the line if it's a comment
					if curLine[0] != "#":
						# See if we're dealing with a URL
						curAddress = curLine.split("/")[-1]
						if len(curAddress) > 0:
							if "." in curAddress:
								listedWorkers.append(curAddress)
							else:
								listedUsers.append(curAddress)
			
		except requests.exceptions.ConnectionError, e:
			print("Could not get this user/worker list due to a connection Error:: \"" + curListUrl + "\"")
		except Exception, e:
			print("Unexpected exception: %s" % str(e))
	
	return (listedUsers, listedWorkers)

#---------------------------------------------------------------------------------------------------
def monitorPool(poolUrls, workers, users, listUrls, sleepSeconds, emailServer, sender, recipients, doBestShareNotification=True, doShowHashRate=True):
	# Build up a list of URLs to monitor
	urlsToMonitor = []
	
	# Add in any explicit pool URLs
	if poolUrls and len(poolUrls > 0):
		urlsToMonitor.extend(poolUrls)
	
	# Initialize an array of monitored addresses. This cache of addresses will be used when
	# a block is found to see if the winner was one of the monitored addresses.
	monitoredAddresses = []
	
	# Construct any worker URLs
	if workers and len(workers) > 0:
		for curWorker in workers:
			curWorkerUrl = urlparse.urljoin(gDefaultPoolUrl + "/workers/", curWorker)
			if curWorkerUrl not in urlsToMonitor:
				urlsToMonitor.append(curWorkerUrl)
			
			# Split off the worker name from the address and add the address to the list
			# of monitored addresses
			curWorkerAddress = curWorker.split(".", 1)[0]
			if curWorkerAddress not in monitoredAddresses:
				monitoredAddresses.append(curWorkerAddress)
	
	# Construct any user URLs
	if users and len(users) > 0:
		for curUser in users:
			curUserUrl = urlparse.urljoin(gDefaultPoolUrl + "/users/", curUser)
			if curUserUrl not in urlsToMonitor:
				urlsToMonitor.append(curUserUrl)
			if curUser not in monitoredAddresses:
				monitoredAddresses.append(curUser)
				
	# We need at least one URL to monitor
	callerProvidedListUrls = True
	if (listUrls and (len(listUrls) > 0)):
		callerProvidedListUrls = True
	if (len(urlsToMonitor) == 0) and not callerProvidedListUrls:
		exitFail("You need at least one pool URL to monitor.")
	
	if gDebug: 
		print("monitoredAddresses: " + str(monitoredAddresses))
	
	# Initialize the dictionary that will keep track of the saved stats. 
	# First we look to see if we have a saved dictionary of best shares in a file.
	savedStats = SavedStats(gSavedStatsFilePath)
		
	# If we haven't initialized the last block found by the pool, do so now and
	# save the stats to disk. This way we can detect when a new block has been found.
	lastFoundBlockCheck = datetime.datetime.now()
	if savedStats.lastBlock == 0:
		(savedStats.lastBlock, ignoreAddress) = wasABlockFound(lastBlock=0)
		if savedStats.lastBlock != 0:
			savedStats.save()
		
	# If any URLs that we wan't to monitor are not in the dictionary, add a skeleton
	# dictionary for it now with a zero best share.
	for curUrl in urlsToMonitor:
		if curUrl not in savedStats.statsDict:
			savedStats.statsDict[curUrl] = { "bestshare": 0.0 }
	
	# Main monitor loop
	if gVerbose:
		p("Monitor starting...")
	while True:
		# If the caller provided a URLs to lists of users or workers, then try to get the lists now.
		if callerProvidedListUrls:
			(listedUsers, listedWorkers) = getUserAndWorkersFromURLs(listUrls)
			for curUser in listedUsers:
				curUserUrl = urlparse.urljoin(gDefaultPoolUrl + "/users/", curUser)
				if curUserUrl not in urlsToMonitor:
					urlsToMonitor.append(curUserUrl)
				if curUser not in monitoredAddresses:
					monitoredAddresses.append(curUser)

			for curWorker in listedWorkers:
				curWorkerUrl = urlparse.urljoin(gDefaultPoolUrl + "/workers/", curWorker)
				if curWorkerUrl not in urlsToMonitor:
					urlsToMonitor.append(curWorkerUrl)
			
				# Split off the worker name from the address and add the address to the list
				# of monitored addresses
				curWorkerAddress = curWorker.split(".", 1)[0]
				if curWorkerAddress not in monitoredAddresses:
					monitoredAddresses.append(curWorkerAddress)

			# If any URLs that we wan't to monitor are not in the dictionary, add a skeleton
			# dictionary for it now with a zero best share.
			for curUrl in urlsToMonitor:
				if curUrl not in savedStats.statsDict:
					savedStats.statsDict[curUrl] = { "bestshare": 0.0 }
		
			# If after getting the lists we have no URLs to monitor, let the user know.
			if len(urlsToMonitor) == 0:
				p("What? The worker list URLs provided did not provide any workers or users.")

		newBestShares = None
		for curUrl in urlsToMonitor:
			try:
				if gDebug: print("Monitor attempting to contact this pool URL: " + curUrl)
			
				# Get the JSON result from the current URL
				r = requests.get(curUrl)
				status = r.status_code
				r.raise_for_status()
				data = r.json()
			
				if gDebug: print("  JSON returned: " + str(data))
			
				# If the best share for the URL is greater than what we remember, then add it
				# to our dictionary of new best shares, then remember the current value.
				if doBestShareNotification:
					curBestShare = data['bestshare']
					savedUrlStatsDict = savedStats.statsDict[curUrl]
					savedBestShare = savedUrlStatsDict['bestshare']
					if curBestShare > savedBestShare:
						if newBestShares == None:
							newBestShares = {}
						newBestShares[curUrl] = curBestShare
			
						# Remember the new JSON dictionary in out saved stats
						savedStats.statsDict[curUrl] = data
				else:
					if gDebug: print("  Caller has disabled best share notification.")
			except requests.exceptions.ConnectionError, e:
				p("Connection Error. Retrying in %i seconds" % sleepSeconds)
				status = -2
			except Exception, e:
				p("Fetching data failed: %s" % str(e))
				status = -2

			if status == 401:
				print (getNowStr() + ": You are not authorized to access the JSON interface for this URL: " + curUrl)
		
		# If it's time to see if the pool found a block, then check now
		newBlock = 0
		foundAddress = None
		foundAddressIsOneOfOurs = False
		if datetime.datetime.now() >= (lastFoundBlockCheck + datetime.timedelta(minutes = gDefaultBlockCheckMinutes)):
			if gDebug: p("Checking to see if the pool found a block...")
			lastFoundBlockCheck = datetime.datetime.now()
			(newBlock, foundAddress) = wasABlockFound(lastBlock=savedStats.lastBlock)

			# HACK TEST to fake out a found block.
			if gDebugPretendWeFoundABlock:
				if gDebugFakeFoundAddress:
					print ("  Pretend we found a block by changing the found address to this test address: " + gDebugFakeFoundAddress)
					foundAddress = gDebugFakeFoundAddress
				else:
					print ("  Pretend we found a block by changing the found address to one of our monitored ones.")
					foundAddress = monitoredAddresses[0]
			
			# If a new block was found, remember it in our stats (which will be saved below)
			if newBlock != 0:
				savedStats.lastBlock = newBlock
		
		# Keep track of email sections so that we can separate them
		emailSectionCount = 0
		
		# If we have new best shares, notify the user and remember the changed stats.
		newBestSharesFound = False
		if newBestShares and (len(newBestShares) > 0):
			newBestSharesFound = True
		if (newBlock != 0) or newBestSharesFound:
			# Save the updated stats
			savedStats.save()

			# Build up the body of the email text.
			subject = "CK Solo Pool: "
			body = ""
			
			# If a block was found, then add that info the the email notification
			appendStr = ""
			if (newBlock != 0) and stringArgCheck(foundAddress):
				p("New block found: " + str(newBlock))
				appendStr = " & "
				if gDebugPretendWeFoundABlock:
					subject = "TEST - " + subject

				subject = subject + "New Block found"
				
				# Add a section separator as needed.
				if emailSectionCount != 0:
					body = body + "\n" + gSeparator + "\n"
				emailSectionCount = emailSectionCount + 1
				
				if gDebugPretendWeFoundABlock:
					body = body + "IMPORTANT! A block was NOT actually found. This email is just a test.\n"
					body = body + "\n"
					
				# Build up the block found section of the email
				body = body + "This lucky address found block number " + str(newBlock) + ":\n\n"
				body = body + foundAddress + "\n"
				body = body + "\n"
				
				# If the address that found the block is one of ours, then this is a big day!
				if foundAddress in monitoredAddresses:
					foundAddressIsOneOfOurs = True
					body = body + "OMG! That's one of your monitored addresses!\n\n"
					body = body + "If it was your address, congratulations! You should go celebrate!\n"
				else:
					body = body + "Unfortunately that was not one of your monitored addresses. Better luck next time...\n"
							
			# If we found new best shares, add that info to the subject and body of the email
			if newBestSharesFound:
				p("New best share found!")
				subject = subject + appendStr + "New best share found"
				appendStr = " & "
					
				# Add a section separator as needed.
				if emailSectionCount != 0:
					body = body + "\n" + gSeparator + "\n"
				emailSectionCount = emailSectionCount + 1

				body = body + "New best share stats for monitored addresses:\n\n"

				# Try to get the current difficulty to include in the email. If we got it, the
				# value will be non-zero.
				curDifficulty = getCurrentDifficulty()
			
				# If we know the current difficulty, put it at the top for reference
				if curDifficulty != 0.0:
					body = body + "Current difficulty: " + str(curDifficulty) + "\n"
				
				# Loop through the new best shares indicating their stats URL, value, and percentage
				# of the current difficulty. Sort the URLs in the dictionary so that there's a consistent order
				# in the email.
				sortedBestSharesUrls = sorted(newBestShares)
				for curUrl in sortedBestSharesUrls:
					curValue = newBestShares[curUrl]
					if len(body) > 0:
						body = body + "\n"
					curStatsAddress = curUrl.split("/")[-1]
					body = body + "  " + curStatsAddress + ":\n"
					body = body + "    New best share:        " + str(newBestShares[curUrl]) + "\n"
					if (curValue != 0.0) and (curDifficulty != 0.0):
						percentOfDifficulty = (curValue / curDifficulty) * 100
						body = body + "    Percent of difficulty: " + str(percentOfDifficulty) + "%\n"

			# If the found address is one that we monitor, and if we're supposed to display the
			# current hash rate, find all the monitored workers or users (by partial match) 
			# and include their hashrate in the email
			if doShowHashRate and (foundAddressIsOneOfOurs or newBestSharesFound):
				# Add a section separator as needed.
				if emailSectionCount != 0:
					body = body + "\n" + gSeparator + "\n"
				emailSectionCount = emailSectionCount + 1

				body = body + "Hash rates of monitored addresses:\n\n"
				
				# We want to show the hash rates of the monitored addresses if a block was
				# found and it was one of our addresses, or if there was a new best share.
				# Build up a sorted list of URLs or addresses that we care about first.
				urlsToReport = []

				# Loop through the monitored addresses looking for any match for the found address
				for curUrl in urlsToMonitor:
					# Add all monitored URLs that contain the found address to the URL list we
					# want to report hashrate for.
					if foundAddress:
						for curUrl in urlsToMonitor:
							if foundAddress in curUrl:
								if curUrl not in urlsToReport:
									urlsToReport.append(curUrl)

					# Add all best share URLs to the list to report
					if newBestSharesFound:
						for key, value in newBestShares.iteritems():
							if key not in urlsToReport:
								urlsToReport.append(key)
										
					# Sort the list
					urlsToReport.sort()
					if gDebug: print("urlsToReport : " + str(urlsToReport))
											
				# Get the hash rate for each address in our sorted list and add it to the 
				# email body
				for curUrl in urlsToReport:
					curAddress = curUrl.split("/")[-1]
					if gDebug:
						print("Getting hash rates from saved stats for this URL: " + curUrl)
						print("  and this address: " + curAddress)
					body = body + "  " + curAddress + ":\n"

					curStatsDict = savedStats.statsDict[curUrl]
					
					# Get the last update time from the stats
					curLastUpdateTimeStr = "Unknown"
					curLastUpdateTime = getLastUpdateTimeFromStatsJson(curStatsDict)
					if curLastUpdateTime:
						curLastUpdateTimeStr = time.strftime('%Y-%m-%d %H:%M:%S', curLastUpdateTime)
						
					body = body + "    Date/Time: " + curLastUpdateTimeStr + "\n"

					# Get the hash rates from the saved stats
					(hashRate5m, hashRate1hr, hashRate1d, hashRate7d) = getHashRatesFromStatsJson(curStatsDict)

					# Add the hashrates to the email body
					body = body + "    5 minute:  " + hashRate5m + "\n"
					body = body + "    1 hour:    " + hashRate1hr + "\n"
					body = body + "    5 day:     " + hashRate1d + "\n"
					body = body + "    7 days:    " + hashRate7d + "\n"
						
					body = body + "\n"
				body = body + "\n"

			# Send the email. If a block was found for our address, then print the email to
			# standard out so that we have a record of it in case the email fails to send.
			if gDebug or gVerbose: 
				p("Sending the new notification email...")
			subject = subject + "!"
			success = emailServer.send(sender, recipients, subject, body, printEmail=foundAddressIsOneOfOurs)
			if not success:
				p("  Could not send the new best share email!")
			elif gDebug or gVerbose:
				p("  Email sent!")
			
			# Clear the new best shares dictionary for the next time through the loop
			newBestShares = None

		# Sleep waiting for the next time to monitor
		time.sleep(sleepSeconds)


#---------------------------------------------------------------------------------------------------
# Script starts here
#---------------------------------------------------------------------------------------------------
# Establish our signal handler
signal.signal(signal.SIGINT, signalHandler)

# Disable annoying InsecurePlatformWarning warnings. Since we only access known URLs, ignoring 
# these warnings should be fine.
requests.packages.urllib3.disable_warnings()

usage="""ckPoolNotify.py [OPTIONS]"""
description="""This script monitors the CK Solo pool, emailing the caller with status changes.
Currently this script monitors the best shares submitted by specified workers or users. If the
best shares improve from historic values saved by this script, an email is sent to the specified
recipients. If you want this script to send from an authenticated email server, then the best way
to get started is to set your password and send a test email. For example: \"./ckPoolNotify.py --user 
<your email address> --setpassword --test\" Once you've successfully received the test email, you 
can run the script in normal monitor mode."""

# Initialize the options parser for this script
parser = OptionParser(usage=usage, description=description)
parser.set_defaults(verbose=False, debug=False, server=gDefaultSmptServer, bestshare=None, showhashrate=None, sleepseconds=gDefaultMonitorSleepSeconds, clear=False, fakefoundaddress=None)
parser.add_option("--verbose",
	action="store_true", dest="verbose",
	help="Verbose output from this script, and from wraptool.")
parser.add_option("-W", "--setpassword",
	action="store_true", dest="setpassword",
	help="If specified, then the password used to authenticate the user for sending emails will be requested and saved in the user's keychain. This option prevents the password from being seen in the command line history. Once saved, the password will be securely obtained from the keychain as needed.")
parser.add_option("-u", "--user",
	action="store", dest="user",
	help="If authentication is used, this is the user to authenticate.")
parser.add_option("-p", "--password",
	action="store", dest="password",
	help="If authentication is used, this is the user's password. This password will be stored in the keychain, so it only needs to be provided once.")
parser.add_option("-f", "--sender",
	action="store", dest="sender",
	help="The sender's email address to use. If no sender's address was provided but a user was provided for an authenticated email server, then the user will be used as the sender.")
parser.add_option("-s", "--server",
	action="store", dest="server",
	help="Email server that will send notifications. Defaults to gmail: \"" + gDefaultSmptServer + "\"")
parser.add_option("-r", "--recipients",
	action="store", dest="recipients",
	help="Email receipients to receive alerts, in comma delimited form: \"one@mail.com,two@mail.com\". If not specified, then this script will use the sender's address as the recipient.")
parser.add_option("-P", "--poolurls",
	action="store", dest="poolurls",
	help="If specified, then these pool URLs will be monitored. The URLs must be complete (including any users or workers). The form specified must be comma delimited like this: \"http://pool1.com/worker1,http://pool1.com/worker2\"")
parser.add_option("-w", "--workers",
	action="store", dest="workers",
	help="If specified, then these workers will be monitored on CK's solo pool. If there's more than one, they must be in comma delimited format like this: \"worker1,worker2\"")
parser.add_option("-U", "--users",
	action="store", dest="users",
	help="If specified, then these users will be monitored on CK's solo pool. If there's more than one, they must be in comma delimited format like this: \"user1,user2\"")
parser.add_option("-l", "--listurls",
	action="store", dest="listurls",
	help="If specified, then these URLs will be used to provide a simple text file of user and worker addresses. If there's more than one URL, they must be in comma delimited formate like this: \"http://url1,http://url2\". The text files referred by the URLs should have one user or worker address per line. You can use this option in combination with the --users or --workers options as desired.")
parser.add_option("-S", "--sleepseconds",
	action="store", dest="sleepseconds",
	help="If specified, then this is the number of seconds to sleep between monitoring events. Defaults to " + str(gDefaultMonitorSleepSeconds) + " seconds.")
parser.add_option("-b", "--bestshare",
	action="store", dest="bestshare",
	help="By default this script notifies receipients if the best share of any monitored workers or users increases. This option allows you to explicitly enable or disable this notification by providing boolean expression including: " + getValidBoolExpresionsStr() + ". For example, this option will disable best share notification: --bestshare \"off\"")
parser.add_option("-H", "--showhashrate",
	action="store", dest="showhashrate",
	help="By default this script will include the hash rates of any monitored workers or users. This option allows you to explicitly enable or disable including the hash rates providing boolean expression including: " + getValidBoolExpresionsStr() + ". For example, this option will disable hash rate info in notification emails: --showhashrate \"off\"")
parser.add_option("-t", "--test",
	action="store_true", dest="test",
	help="If specified, then send a test message to the recipients using the senders credentials, then quit. If a password is provided, it will be saved in the current user's keychain.")
parser.add_option("-c", "--clear",
	action="store_true", dest="clear",
	help="If specified, then clear any saved history. This will result in finding new best share data and sending a new notification email.")
parser.add_option("-F", "--fakefoundaddress",
	action="store", dest="fakefoundaddress",
	help="If you pass an address via this option, then the script will go into test mode where it will pretend that this address found a block. Within " + str(gDefaultBlockCheckMinutes) + " minutes an email will be sent indicate that this address found a block. This option is for development and testing only.")
parser.add_option("--debug",
	action="store_true", dest="debug",
	help="Turn on debugging output for this script.")

# Parse the incomming arguments.
(options, args) = parser.parse_args()

# See if we're debugging this script
#options.debug=True
if options.debug:
	gDebug = True
else:
	gDebug = False

if gDebug:
	print("After options parsing:")
	print("	 options:", options)
	print("	 args...:", args)

# If the verbose option was specified, we'll display verbose output
if options.verbose:
	gVerbose = True
else:
	gVerbose = False

# If the caller wants us to clear history, then delete the saved data file.
if options.clear:
	if os.path.exists(gSavedStatsFilePath):
		print("Deleting the saved stats data file located here: \"" + gSavedStatsFilePath + "\"")
		os.remove(gSavedStatsFilePath)

# Make sure the caller specifies a user account to send emails. If a user was specified for
# authentication and no sender was specified, then user the user as the sender.
sender = options.sender
if not stringArgCheck(sender):
	if stringArgCheck(options.user):
		sender = options.user
	else:
		exitFail("You must specify the sending address for notifications.")

# Make sure the caller specifies some email recipients
recipients=[]
if stringArgCheck(options.recipients):
	recipients = options.recipients.split(",")
else:
	recipients.append(sender)
	if gDebug: print("Using the sender as the recipient: " + str(recipients))
	
# Make sure we have an smtp server.
if not stringArgCheck(options.server):
	exitFail("You must specify an SMTP server that will be used to send emails.")
	
# If the caller wants to set the password in the keychain, then do that now, preventing the keychain
# from being visible in the command line history or terminal window.
password = None
if options.setpassword:
	if not stringArgCheck(options.user):
		exitFail("You must specify a user in order to set the password.")
	print("Please enter the password used to authenticate the user for sending emails.")
	password = getpass.getpass()
	setPassword(options.user, password)
	
# If the caller specified a user for email authentication, then we will also need a password.
# If a password was specified, then save it in the keychain. If a password was not specified,
# then try to retrieve it from the keychain.
if stringArgCheck(options.user):
	if not password:
		password = setOrGetPassword(options.user, options.password)

# Initialize an email server object. We'll need it whether we're in test mode or monitor mode
emailServer = EmailServer(serverUrl=options.server, user=options.user, password=password)
	
# If the caller want's to send a test email, then try now
if options.test:
	success = emailServer.send(sender=sender, recipients=recipients, subject="Test message from " + gScriptName, body="I'll bet you wish this email had some interesting statistics, but instead it's just a test.")
	if success:
		print("  Test message successfully sent.")
	else:
		exitFail("Error sending the test email!")
else:
	# First see if the user specified any fully formed URLs
	poolUrls = []
	if stringArgCheck(options.poolurls):
		poolUrls = options.poolurls.split(",")
	
	# Next see if the caller specified any workers
	workers = []
	if stringArgCheck(options.workers):
		workers = options.workers.split(",")
	
	# Next see if the caller specified any users
	users = []
	if stringArgCheck(options.users):
		users = options.users.split(",")
	
	# If the caller specified URLs that contain a list of workers or users, then split them out
	# to pass to the monitor function.
	listurls = []
	if stringArgCheck(options.listurls):
		listurls = options.listurls.split(",")
	
	# If the caller specified no pools, workers, or users, then we can't do anything
	if (len(poolUrls) == 0) and (len(workers) == 0) and (len(users) == 0) and (len(listurls) == 0):
		exitFail("You must specify a worker, user, pool URL, or monitor list URL. See the help documentation via --help.")
	
	# If a best share notification override was set, then evaluate it now to determine if we're going
	# to notify for best share increases
	doBestShareNotification = True
	if stringArgCheck(options.bestshare):
		(doBestShareNotification, validExpression) = evaluateBoolExpression(options.bestshare)
		if not validExpression:
			exitFailBadBooleanExpression("You provided an invalid boolean expression for the --bestshare option", options.bestshare)
		if gDebug:
			if doBestShareNotification:
				print("Caller has explicitly enabled best share notification.")
			else:
				print("Caller has explicitly disabled best share notification.")

	# If a show hash rate override was set, then evaluate it now to determine if we're going
	# to include hash rate info in notification emails
	doShowHashRate = True
	if stringArgCheck(options.showhashrate):
		(doShowHashRate, validExpression) = evaluateBoolExpression(options.showhashrate)
		if not validExpression:
			exitFailBadBooleanExpression("You provided an invalid boolean expression for the --showhashrate option", options.showhashrate)
		if gDebug:
			if doShowHashRate:
				print("Caller has explicitly enabled the inclusion of hash rate info in emails.")
			else:
				print("Caller has explicitly disabled the inclusion of hash rate info in emails.")
	
	# If the caller wants to test the finding of a block, then set the debug block info so that the
	# monitor will pretend to find a block and sent the corresponding email.
	if stringArgCheck(options.fakefoundaddress):
		gDebugPretendWeFoundABlock = True
		gDebugFakeFoundAddress = options.fakefoundaddress
		print("This script will pretend that this address found a block: " + gDebugFakeFoundAddress)

	# Start the monitor. This will run forever until the script is quit.
	monitorPool(poolUrls=poolUrls, workers=workers, users=users, listUrls=listurls, sleepSeconds=options.sleepseconds, emailServer=emailServer, sender=sender, recipients=recipients, doBestShareNotification=doBestShareNotification, doShowHashRate=doShowHashRate)
