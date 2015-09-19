# CK Solo Pool Notification Script — Read Me

## By edonkey:	September 15, 2015
## Donations:  	18wQtEDmhur2xAd3oE8qgrZbpCDeuMsdQW


## Introduction

The ckPoolNotify.py script monitors the CK solo pool, emailing the caller with status changes. 

Currently this script monitors two events. First, if a block is found then a notification email is sent. If the found block is from any of your monitored addresses, the script congratulates you. Otherwise it wishes you better luck next time.

Second you will receive a notification if the best shares submitted by your specified workers or users has improved from previous values. While past success is no indication of future success, this does provide a little bit of feedback that something is happening. And it's kind of fun to cheer on your miners.


## Installation

This script requires Python 2.6 or greater. Depending on your platform, you may also need to install certain Python libraries, including “keyring” for secure password storage.

In order to install the required Python libraries, you can use any Python package installation tools that you wish. I prefer setuptools, which is what we’ll use for the installation examples below.

Assuming that you have setuptools already installed, here’s how to install the required libraries (the ‘sudo’ is needed for Mac OS X; it may or may not be needed for your platform):

	sudo easy_install -U requests
	sudo easy_install -U keyring

To verify your installation, try getting the script’s help docs. If this works with no error, then the script is ready to use:

	ckPoolNotify.py --help


If you don’t have setuptools installed, please see below for installation on your platform.


### Linux

Here’s a sample command line that will install the setuptools under Ubuntu:

	sudo apt-get install python-setuptools

If you're using a different Linux distribution with a different package manager, you'll have to translate the above into the command lines for that package manager.


### Macintosh

If you're on a Macintosh, there is no native package manager. If you don't already have the setuptools installed, you must download and install it. Here's how:

	curl https://bootstrap.pypa.io/ez_setup.py -o ez_setup.py
	sudo python ez_setup.py


### Windows

If you're on Windows and have not installed the setuptools package, please follow the installation instructions here for your version of Windows:

	https://pypi.python.org/pypi/setuptools


## Email Configuration

Once installed, the script is ready to use. However since the script sends emails, it’s a good idea to send a test email first to make sure you’ve got the correct email configuration and credentials.


### Authenticated Email

Most people will be sending emails using an authenticated email server. This means that a user and password must be provided to the email server in order to send. If you provide a password to this script, it will store it securely in the local keychain for your operating system.

One note about Gmail users. It’s a good idea to use Gmail’s two factor authentication. Assuming that you have configured two factor security, then you will need to go to your Gmail account and create an application password for this script. Once you have that application password, you can pass it to the script instead of your actual Gmail account password. See Google’s documentation for setting up application passwords.

For security reasons you probably don’t want to provide your password on the command line to this script, which would leave your password in the command line history. You can avoid this by using the  --setpassword option.

Here’s an example of how to set your password and send a test email without exposing your password on the command line (provide your own path to the script and your own email user and server):

	./ckPoolNotify.py --server "smtp.gmail.com:587" --user my_email@gmail.com --setpassword --test

You will be prompted for your password at this point, but it will not be visible in the terminal window.

Note that if you have a Gmail address, you don’t have to specify the server because the script defaults to the Gmail server URL.

Once you’ve successfully sent a test email to your account, your password will be set in your local keychain. You will not need to specify your password to the script again, unless you change your password.


### Unauthenticated Email

If you are using an unauthenticated email server, then no user name or password is needed. Generally this will be a rare case, unless you’re running your own email server.

If you have an unauthenticated email server, then you can send a test email with a command line like the following:

	./ckPoolNotify.py --server <your server> --sender <your sender email> --recipients <your recipient email> --test


## Notification Configuration

Once you’ve successfully received the test email message, it’s time to use the script itself. To do that, you call the script with the same email credentials (without the password because that will be retrieved by the script from your keychain), plus the worker or user addresses that you wish to monitor.

Here’s an example (note that it should be all on one line):

	./ckPoolNotify.py --verbose --server "smtp.gmail.com:587" --user my_email@gmail.com --workers "1JiWuyX94wrCr7JhkAn7x5qNMCEef1KhqX.edonkeystick" --users "1JiWuyX94wrCr7JhkAn7x5qNMCEef1KhqX"

Note that you can specify multiple workers or users by using a comma separator. For example:

	--workers "worker1,worker2,worker3"

If this is the first time you’ve called the script, it will send you an email with the current best shares, then it will “remember” the best shares in a local file. You won’t receive another notification email until there’s a new best share, or if you clear the local storage with the “--clear” command.

The script will run in a loop forever until you quit it.

Note that if you don't want best share notifications, you can use this override option to disable it:

	--bestshare off


## Daemon Configuration

In some cases you may want to run the notification script automatically at boot as a daemon rather than manually launching it from a command line window. Depending on the platform you’re using, there will be a number of ways to configure a script to be a daemon. 


### Macintosh Daemon

For now, this section discusses how to set up a daemon for Mac OS X. Please follow these steps if you wish to configure the script to run as a daemon:

1. The script should be run as a regular user, not as root. To do that use a text editor to open the org.edonkey.mining.ckpoolnotify.plist file, changing REPLACE_ME to your user. If you don’t know what your user name is, run the following command in at terminal window: 

		echo $USER

2. Edit the ckPoolNotify.sh script (note that this is a shell script, not the main, general purpose Python script), setting your email credentials, plus the workers and users you want to monitor.

3. Delete the scripts stats file (which will force an email send the next time the script is run) by entering the following command in a Terminal window:

		rm ~/.ckPoolNotify_SavedStats

4. Test the shell script by dragging the edited ckPoolNotify.sh script to a Terminal window and hitting the return key. The script should run without errors. If it does, wait for it to send the email, then quit the script by hitting control c. At this point, you should have received the notification email.

5. Copy the “ckPoolNotify” folder to /Library/Application Support. To do this, use this command line (substituting your ckPoolNotify folder path if it’s not in your home directory; you will be asked for your admin credentials to perform the copy):

		sudo cp -rp ~/ckPoolNotify /Library/Application\ Support

6. From a Terminal window, enter the following commands:

		rm ~/.ckPoolNotify_SavedStats

		sudo cp /Library/Application\ Support/ckPoolNotify/org.edonkey.mining.ckpoolnotify.plist /Library/LaunchDaemons

		sudo launchctl load /Library/LaunchDaemons/org.edonkey.mining.ckpoolnotify.plist

If everything worked, then the script will be running as a Daemon under your user, and an email will be sent again because we deleted the saved stats file. From this point on, the daemon will automatically run at boot on your machine.

If you have problems with the daemon, the following commands will show you the text output from the script (the first one is normal output and the second one is for errors):

	cat /tmp/ckpoolnotify.stdout 
	cat /tmp/ckpoolnotify.stderr

If you want to remove the daemon, then enter these commands in a Terminal window:

	sudo launchctl unload /Library/LaunchDaemons/org.edonkey.mining.ckpoolnotify.plist
	sudo rm /Library/LaunchDaemons/org.edonkey.mining.ckpoolnotify.plist

At this point the daemon will be unloaded and will not be loaded on subsequent boots.

