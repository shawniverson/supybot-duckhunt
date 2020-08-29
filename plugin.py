###
# Copyright (c) 2012, Matthias Meusburger
# All rights reserved.
#
# # Modified by spammy, because he likes ducks and they should be saved
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

from supybot.commands import *
import supybot.plugins as plugins
import supybot.callbacks as callbacks
import supybot.schedule as schedule
import supybot.ircdb as ircdb
import supybot.ircmsgs as ircmsgs
import supybot.log as log
import supybot.conf as conf


import threading, random, pickle, os, time, datetime


class DuckHunt(callbacks.Plugin):
    """
    A DuckHunt game for supybot. Use the "start" command to start a game.
    The bot will randomly launch ducks. Whenever a duck is launched, the first
    person to use the "bang" command wins a point. Using the "bang" command
    when there is no duck launched costs a point.
    """

    threaded = True

    # Those parameters are per-channel parameters
    started = {}                # Has the hunt started?
    duck = {}                   # Is there currently a duck to shoot?
    shoots = {}                 # Number of successful shoots (and saves) in a hunt
    shootscores = {}            # Shoot scores for the current hunt
    savescores = {}             # Save scores for the current hunt
    times = {}                  # Elapsed time since the last duck was launched
    channelshootscores = {}     # Saved scores for the channel
    channelsavescores = {}      # Saved scores for the channel
    toptimes = {}               # Times for the current hunt
    channeltimes = {}           # Saved times for the channel
    worsttimes = {}             # Worst times for the current hunt
    channelworsttimes = {}      # Saved worst times for the channel
    averagetime = {}            # Average shooting time for the current hunt
    fridayMode = {}             # Are we on friday mode? (automatic)
    manualFriday = {}           # Are we on friday mode? (manual)
    missprobability = {}        # Probability to miss a duck when shooting
    week = {}                   # Scores for the week
    channelweekshots = {}       # Saved shot scores for the week
    channelweeksaves = {}       # Saved save scores for the week
    leadershooter = {}          # Who is the leader shooter for the week?
    leadersaver = {}            # Who is the leader shooter for the week?
    reloading = {}              # Who is currently reloading?
    reloadtime = {}             # Time to reload after shooting (in seconds)

    # Does a duck needs to be launched?
    lastSpoke = {}
    minthrottle = {}
    maxthrottle = {}
    throttle = {}

    # Where to save scores?
    fileprefix = "DuckHunt_"
    path = conf.supybot.directories.data

    # Enable the 'dbg' command, which launch a duck, if true
    debug = 0

    # Other params
    perfectbonus = 5 # How many extra-points are given when someones does a perfect hunt?
    toplist = 5      # How many high{scores|times} are displayed by default?
    dow = int(time.strftime("%u")) # Day of week
    woy = int(time.strftime("%V")) # Week of year
    year = time.strftime("%Y") 
    dayname = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Caturday', 'Saturday', 'Sunday']


    def _calc_scores(self, channel):
        """
        Adds new scores and times to the already saved ones
        """

        # shootscores
        # Adding current scores to the channel scores
        for player in list(self.shootscores[channel].keys()):
            if not player in self.channelshootscores[channel]:
                # It's a new player
                self.channelshootscores[channel][player] = self.shootscores[channel][player]
            else:
                # It's a player that already has a saved score
                self.channelshootscores[channel][player] += self.shootscores[channel][player]

        # savescores
        # Adding current scores to the channel scores
        for player in list(self.savescores[channel].keys()):
            if not player in self.channelsavescores[channel]:
                # It's a new player
                self.channelsavescores[channel][player] = self.savescores[channel][player]
            else:
                # It's a player that already has a saved score
                self.channelsavescores[channel][player] += self.savescores[channel][player]

        # times
        # Adding times scores to the channel scores
        for player in list(self.toptimes[channel].keys()):
            if not player in self.channeltimes[channel]:
                # It's a new player
                self.channeltimes[channel][player] = self.toptimes[channel][player]
            else:
                # It's a player that already has a saved score
                # And we save the time of the current hunt if it's better than it's previous time
                if(self.toptimes[channel][player] < self.channeltimes[channel][player]):
                    self.channeltimes[channel][player] = self.toptimes[channel][player]

        # worst times
        # Adding worst times scores to the channel scores
        for player in list(self.worsttimes[channel].keys()):
            if not player in self.channelworsttimes[channel]:
                # It's a new player
                self.channelworsttimes[channel][player] = self.worsttimes[channel][player]
            else:
                # It's a player that already has a saved score
                # And we save the time of the current hunt if it's worst than it's previous time
                if(self.worsttimes[channel][player] > self.channelworsttimes[channel][player]):
                    self.channelworsttimes[channel][player] = self.worsttimes[channel][player]

        # week shoot scores
        for player in list(self.shootscores[channel].keys()):
            #FIXME: If the hunt starts a day and ends the day after, this will produce an error:
            if not player in self.channelweekshots[channel][self.woy][self.dow]:
                # It's a new player
                self.channelweekshots[channel][self.woy][self.dow][player] = self.shootscores[channel][player]
            else:
                # It's a player that already has a saved score
                self.channelweekshots[channel][self.woy][self.dow][player] += self.shootscores[channel][player]

        # week save scores
        for player in list(self.savescores[channel].keys()):
            #FIXME: If the hunt starts a day and ends the day after, this will produce an error:
            if not player in self.channelweeksaves[channel][self.woy][self.dow]:
                # It's a new player
                self.channelweeksaves[channel][self.woy][self.dow][player] = self.savescores[channel][player]
            else:
                # It's a player that already has a saved score
                self.channelweeksaves[channel][self.woy][self.dow][player] += self.savescores[channel][player]


    def _write_scores(self, channel):
        """
        Write scores and times to the disk
        """

        # shootscores
        outputfile = open(self.path.dirize(self.fileprefix + channel + ".shootscores"), "wb")
        pickle.dump(self.channelshootscores[channel], outputfile)
        outputfile.close()

        # savescores
        outputfile = open(self.path.dirize(self.fileprefix + channel + ".savescores"), "wb")
        pickle.dump(self.channelsavescores[channel], outputfile)
        outputfile.close()

        # times
        outputfile = open(self.path.dirize(self.fileprefix + channel + ".times"), "wb")
        pickle.dump(self.channeltimes[channel], outputfile)
        outputfile.close()

        # worst times
        outputfile = open(self.path.dirize(self.fileprefix + channel + ".worsttimes"), "wb")
        pickle.dump(self.channelworsttimes[channel], outputfile)
        outputfile.close()

        # week shot scores
        outputfile = open(self.path.dirize(self.fileprefix + channel + self.year + ".weekshots"), "wb")
        pickle.dump(self.channelweekshots[channel], outputfile)
        outputfile.close()

        # week save scores
        outputfile = open(self.path.dirize(self.fileprefix + channel + self.year + ".weeksaves"), "wb")
        pickle.dump(self.channelweeksaves[channel], outputfile)
        outputfile.close()

    def _read_scores(self, channel):
        """
        Reads scores and times from disk
        """
        filename = self.path.dirize(self.fileprefix + channel)
        # shootscores
        if not self.channelshootscores.get(channel):
            if os.path.isfile(filename + ".shootscores"):
                inputfile = open(filename + ".shootscores", "rb")
                self.channelshootscores[channel] = pickle.load(inputfile)
                inputfile.close()

        # savescores
        if not self.channelsavescores.get(channel):
            if os.path.isfile(filename + ".savescores"):
                inputfile = open(filename + ".savescores", "rb")
                self.channelsavescores[channel] = pickle.load(inputfile)
                inputfile.close()

        # times
        if not self.channeltimes.get(channel):
            if os.path.isfile(filename + ".times"):
                inputfile = open(filename + ".times", "rb")
                self.channeltimes[channel] = pickle.load(inputfile)
                inputfile.close()

        # worst times
        if not self.channelworsttimes.get(channel):
            if os.path.isfile(filename + ".worsttimes"):
                inputfile = open(filename + ".worsttimes", "rb")
                self.channelworsttimes[channel] = pickle.load(inputfile)
                inputfile.close()

        # week shots
        if not self.channelweekshots.get(channel):
            if os.path.isfile(filename + self.year + ".weekshots"):
                inputfile = open(filename + self.year + ".weekshots", "rb")
                self.channelweekshots[channel] = pickle.load(inputfile)
                inputfile.close()

         # week saves
        if not self.channelweeksaves.get(channel):
            if os.path.isfile(filename + self.year + ".weeksaves"):
                inputfile = open(filename + self.year + ".weeksaves", "rb")
                self.channelweeksaves[channel] = pickle.load(inputfile)
                inputfile.close()


    def _initdayweekyear(self, channel):
        self.dow = int(time.strftime("%u")) # Day of week
        self.woy = int(time.strftime("%V")) # Week of year
        year = time.strftime("%Y") 

        # Init week shot scores
        try:
            self.channelweekshots[channel]
        except:
            self.channelweekshots[channel] = {}
        try:
            self.channelweekshots[channel][self.woy]
        except:
            self.channelweekshots[channel][self.woy] = {}
        try:
            self.channelweekshots[channel][self.woy][self.dow]
        except:
            self.channelweekshots[channel][self.woy][self.dow] = {}

          # Init week save scores
        try:
            self.channelweeksaves[channel]
        except:
            self.channelweeksaves[channel] = {}
        try:
            self.channelweeksaves[channel][self.woy]
        except:
            self.channelweeksaves[channel][self.woy] = {}
        try:
            self.channelweeksaves[channel][self.woy][self.dow]
        except:
            self.channelweeksaves[channel][self.woy][self.dow] = {}


    def _initthrottle(self, irc, msg, args, channel):

        self._initdayweekyear(channel)
            
        if not self.leadershooter.get(channel):
            self.leadershooter[channel] = None

        if not self.leadersaver.get(channel):
            self.leadersaver[channel] = None

        # autoFriday?
        if (not self.fridayMode.get(channel)):
            self.fridayMode[channel] = False

        if (not self.manualFriday.get(channel)):
            self.manualFriday[channel] = False


        if self.registryValue('autoFriday', channel) == True:
            if int(time.strftime("%w")) == 5 and int(time.strftime("%H")) > 8 and int(time.strftime("%H")) < 17:
                self.fridayMode[channel] = True
            else:
                self.fridayMode[channel] = False

        # Miss probability
        if self.registryValue('missProbability', channel):
            self.missprobability[channel] = self.registryValue('missProbability', channel)
        else:
            self.missprobability[channel] = 0.2

        # Reload time
        if self.registryValue('reloadTime', channel):
            self.reloadtime[channel] = self.registryValue('reloadTime', channel)
        else:
            self.reloadtime[channel] = 5

        if self.fridayMode[channel] == False and self.manualFriday[channel] == False:
            # Init min throttle[currentChannel] and max throttle[currentChannel]
            if self.registryValue('minthrottle', channel):
                self.minthrottle[channel] = self.registryValue('minthrottle', channel)
            else:
                self.minthrottle[channel] = 30

            if self.registryValue('maxthrottle', channel):
                self.maxthrottle[channel] = self.registryValue('maxthrottle', channel)
            else:
                self.maxthrottle[channel] = 300

        else:
            self.minthrottle[channel] = 3
            self.maxthrottle[channel] = 60

        self.throttle[channel] = random.randint(self.minthrottle[channel], self.maxthrottle[channel])


    def start(self, irc, msg, args):
        """
        Starts the hunt
        """

        currentChannel = msg.args[0]
        if irc.isChannel(currentChannel):

            if(self.started.get(currentChannel) == True):
                irc.reply("There is already a hunt right now!")
            else:

                # First of all, let's read the score if needed
                self._read_scores(currentChannel)

                self._initthrottle(irc, msg, args, currentChannel)

                # Init saved shootscores
                try:
                    self.channelshootscores[currentChannel]
                except:
                    self.channelshootscores[currentChannel] = {}

                # Init saved savescores
                try:
                    self.channelsavescores[currentChannel]
                except:
                    self.channelsavescores[currentChannel] = {}

                # Init saved times
                try:
                    self.channeltimes[currentChannel]
                except:
                    self.channeltimes[currentChannel] = {}

                # Init saved times
                try:
                    self.channelworsttimes[currentChannel]
                except:
                    self.channelworsttimes[currentChannel] = {}

                # Init times
                self.toptimes[currentChannel] = {}
                self.worsttimes[currentChannel] = {}

                # Init bangdelay
                self.times[currentChannel] = False

                # Init lastSpoke
                self.lastSpoke[currentChannel] = time.time()

                # Reinit current hunt shootscores
                if self.shootscores.get(currentChannel):
                    self.shootscores[currentChannel] = {}

                # Reinit current hunt savescores
                if self.savescores.get(currentChannel):
                    self.savescores[currentChannel] = {}

                # Reinit reloading
                self.reloading[currentChannel] = {}

                # No duck launched
                self.duck[currentChannel] = False

                # Hunt started
                self.started[currentChannel] = True

                # Init shoots
                self.shoots[currentChannel] = 0

                # Init averagetime
                self.averagetime[currentChannel] = 0;

                # Init schedule

                # First of all, stop the scheduler if it was still running
                try:
                    schedule.removeEvent('DuckHunt_' + currentChannel)
                except KeyError:
                    pass

                # Then restart it
                def myEventCaller():
                    self._launchEvent(irc, msg)
                try:
                    schedule.addPeriodicEvent(myEventCaller, 5, 'DuckHunt_' + currentChannel, False)
                except AssertionError:
                    pass

                irc.reply("The hunt starts now!")
        else:
                irc.error('You have to be on a channel')
    start = wrap(start)


    def _launchEvent(self, irc, msg):
        currentChannel = msg.args[0]
        now = time.time()
        if irc.isChannel(currentChannel):
            if(self.started.get(currentChannel) == True):
                if (self.duck[currentChannel] == False):
                    if now > self.lastSpoke[currentChannel] + self.throttle[currentChannel]:
                        self._launch(irc, msg, '')



    def stop(self, irc, msg, args):
        """
        Stops the current hunt
        """

        currentChannel = msg.args[0]
        if irc.isChannel(currentChannel):
            if (self.started.get(currentChannel) == True):
                self._end(irc, msg, args)

            # If someone uses the stop command,
            # we stop the scheduler, even if autoRestart is enabled
            try:
                schedule.removeEvent('DuckHunt_' + currentChannel)
            except KeyError:
                irc.reply('Error: the spammer wasn\'t running! This is a bug.')
            else:
                irc.reply('Nothing to stop: there\'s no hunt right now.')
        else:
            irc.error('You have to be on a channel')
    stop = wrap(stop)

    def fridaymode(self, irc, msg, args, channel, status):
        """
        [<status>] 
        Enable/disable friday mode! (there are lots of ducks on friday :))
        """
        if irc.isChannel(channel):

            if (status == 'status'):
                irc.reply('Manual friday mode for ' + channel + ' is ' + str(self.manualFriday.get(channel)));
                irc.reply('Auto friday mode for ' + channel + ' is ' + str(self.fridayMode.get(channel)));
            else:
                if (self.manualFriday.get(channel) == None or self.manualFriday[channel] == False):
                    self.manualFriday[channel] = True
                    irc.reply("Friday mode is now enabled! Shoot alllllllllllll the ducks!")
                else:
                    self.manualFriday[channel] = False
                    irc.reply("Friday mode is now disabled.")

            self._initthrottle(irc, msg, args, channel)
        else:
            irc.error('You have to be on a channel')


    fridaymode = wrap(fridaymode, ['channel', 'admin', optional('anything')])

    def launched(self, irc, msg, args):
        """
        Is there a duck right now?
        """

        currentChannel = msg.args[0]
        if irc.isChannel(currentChannel):
            if(self.started.get(currentChannel) == True):
                if(self.duck[currentChannel] == True):
                    irc.reply("There is currently a duck! You can shoot it with the 'bang' command or save with the 'bef' command")
                else:
                    irc.reply("There is no duck right now! Wait for one to be launched!")
            else:
                irc.reply("There is no hunt right now! You can start a hunt with the 'start' command")
        else:
            irc.error('You have to be on a channel')
    launched = wrap(launched)



    def score(self, irc, msg, args, nick):
        """
        <nick>

        Shows the score for a given nick
        """
        currentChannel = msg.args[0]
        if irc.isChannel(currentChannel):
            self._read_scores(currentChannel)
            try:
                self.channelshootscores[currentChannel]
            except:
                self.channelshootscores[currentChannel] = {}
            try:
                self.channelsavescores[currentChannel]
            except:
                self.channelsavescores[currentChannel] = {}

            try:
                irc.reply("\_x< Shot score: %s " % (self.channelshootscores[currentChannel][nick]))
            except:
                irc.reply("There is no shot score for %s on %s" % (nick, currentChannel))
            try:
                irc.reply("\_O< Save score: %s " % (self.channelsavescores[currentChannel][nick]))
            except:
                irc.reply("There is no save score for %s on %s" % (nick, currentChannel))
        else:
            irc.error('You have to be on a channel')

    score = wrap(score, ['nick'])



    def mergescores(self, irc, msg, args, channel, nickto, nickfrom):
        """
        [<channel>] <nickto> <nickfrom>
        
        nickto gets the points of nickfrom and nickfrom is removed from the scorelist
        """
        if irc.isChannel(channel):
            self._read_scores(channel)

            # Total shoot scores
            try:
                self.channelshootscores[channel][nickto] += self.channelshootscores[channel][nickfrom]
                del self.channelshootscores[channel][nickfrom]
                self._write_scores(channel)
                irc.reply("Total shoot scores merged")

            except:
                irc.error("Can't merge total shoot scores")

            # Total save scores
            try:
                self.channelsavescores[channel][nickto] += self.channelsavescores[channel][nickfrom]
                del self.channelsavescores[channel][nickfrom]
                self._write_scores(channel)
                irc.reply("Total save scores merged")

            except:
                irc.error("Can't merge total save scores")


            self._initdayweekyear(channel)
            day = self.dow
            week = self.woy
            
            # Day shot scores
            try:            
                try:
                    self.channelweekshots[channel][week][day][nickto] += self.channelweekshots[channel][week][day][nickfrom]
                except:
                    self.channelweekshots[channel][week][day][nickto] = self.channelweekshots[channel][week][day][nickfrom]

                del self.channelweekshots[channel][week][day][nickfrom]
                self._write_scores(channel)
                irc.reply("Day shot scores merged")

            except:
                irc.error("Can't merge day shot scores")

            # Day save scores
            try:            
                try:
                    self.channelweeksaves[channel][week][day][nickto] += self.channelweeksaves[channel][week][day][nickfrom]
                except:
                    self.channelweeksaves[channel][week][day][nickto] = self.channelweeksaves[channel][week][day][nickfrom]

                del self.channelweeksaves[channel][week][day][nickfrom]
                irc.reply("Day shot saves merged")

            except:
                irc.error("Can't merge day shot scores")

            self._write_scores(channel)

        else:
            irc.error('You have to be on a channel')

    mergescores = wrap(mergescores, ['channel', 'nick', 'nick', 'admin'])


    def mergetimes(self, irc, msg, args, channel, nickto, nickfrom):
        """
        [<channel>] <nickto> <nickfrom>
        
        nickto gets the best time of nickfrom if nickfrom time is better than nickto time, and nickfrom is removed from the timelist. Also works with worst times. 
        """
        if irc.isChannel(channel):
            try:
                self._read_scores(channel)

                # Merge best times
                if self.channeltimes[channel][nickfrom] < self.channeltimes[channel][nickto]:
                    self.channeltimes[channel][nickto] = self.channeltimes[channel][nickfrom]
                del self.channeltimes[channel][nickfrom]

                # Merge worst times
                if self.channelworsttimes[channel][nickfrom] > self.channelworsttimes[channel][nickto]:
                    self.channelworsttimes[channel][nickto] = self.channelworsttimes[channel][nickfrom]
                del self.channelworsttimes[channel][nickfrom]

                self._write_scores(channel)

                irc.replySuccess()

            except:
                irc.replyError()


        else:
            irc.error('You have to be on a channel')


    mergetimes = wrap(mergetimes, ['channel', 'nick', 'nick', 'admin'])


    def rmtime(self, irc, msg, args, channel, nick):
        """
        [<channel>] <nick>
        
        Remove <nick>'s best time
        """
        if irc.isChannel(channel):
            self._read_scores(channel)
            del self.channeltimes[channel][nick]
            self._write_scores(channel)
            irc.replySuccess()

        else:
            irc.error('Are you sure ' + str(channel) + ' is a channel?')

    rmtime = wrap(rmtime, ['channel', 'nick', 'admin'])



    def rmscore(self, irc, msg, args, channel, nick):
        """
        [<channel>] <nick>
        
        Remove <nick>'s score
        """
        if irc.isChannel(channel):
            try:
                self._read_scores(channel)
                del self.channelshootscores[channel][nick]
                del self.channelsavescores[channel][nick]
                self._write_scores(channel)
                irc.replySuccess()

            except:
                irc.replyError()

        else:
            irc.error('Are you sure this is a channel?')

    rmscore = wrap(rmscore, ['channel', 'nick', 'admin'])


    def dayscores(self, irc, msg, args, channel):
        """
        [<channel>]
        
        Shows the score list of the day for <channel>. 
        """

        if irc.isChannel(channel):

            self._read_scores(channel)
            self._initdayweekyear(channel)
            day = self.dow
            week = self.woy

            if self.channelweekshots.get(channel):
                if self.channelweekshots[channel].get(week):
                    if self.channelweekshots[channel][week].get(day):
                    # Getting all scores, to get the winner of the week
                        msgstring = ''
                        scores = sorted(iter(self.channelweekshots[channel][week][day].items()), key=lambda k_v2:(k_v2[1],k_v2[0]), reverse=True)
                        for item in scores:
                            msgstring += "x" + item[0] + "x: "+ str(item[1]) + " | "

                        if msgstring != "":
                            irc.reply("Shot scores for today: " + msgstring)
                        else:
                            irc.reply("There aren't any day shot scores for today yet.")
                    else:
                        irc.reply("There aren't any day shot scores for today yet.")
                else:
                    irc.reply("There aren't any day shot scores for today yet.")
            else:
                irc.reply("There aren't any day shot scores for this channel yet.")
            
            if self.channelweeksaves.get(channel):
                if self.channelweeksaves[channel].get(week):
                    if self.channelweeksaves[channel][week].get(day):
                    # Getting all scores, to get the winner of the week
                        msgstring = ''
                        scores = sorted(iter(self.channelweeksaves[channel][week][day].items()), key=lambda k_v2:(k_v2[1],k_v2[0]), reverse=True)
                        for item in scores:
                            msgstring += "x" + item[0] + "x: "+ str(item[1]) + " | "

                        if msgstring != "":
                            irc.reply("Save scores for today: " + msgstring)
                        else:
                            irc.reply("There aren't any day save scores for today yet.")
                    else:
                        irc.reply("There aren't any day save scores for today yet.")
                else:
                    irc.reply("There aren't any day save scores for today yet.")
            else:
                irc.reply("There aren't any day save scores for this channel yet.")

        else:
            irc.reply("Are you sure this is a channel?")
    dayscores = wrap(dayscores, ['channel'])



    def weekscores(self, irc, msg, args, week, nick, channel):
        """
        [<week>] [<nick>] [<channel>]
        
        Shows the score list of the week for <channel>. If <nick> is provided, it will only show <nick>'s scores.
        """

        if irc.isChannel(channel):

            self._read_scores(channel)
            weekscores = {}

            if (not week):
                week = self.woy

            if self.channelweekshots.get(channel):
                if self.channelweekshots[channel].get(week):
                    # Showing the winner for each day
                    if not nick:
                        msgstring = ''
                        # for each day of week
                        for i in (1,2,3,4,5,6,7):
                            if self.channelweekshots[channel][week].get(i):
                                # Getting winner of the day
                                winnernick, winnerscore = max(iter(self.channelweekshots[channel][week][i].items()), key=lambda k_v:(k_v[1],k_v[0]))
                                msgstring += self.dayname[i - 1] + ": x" + winnernick + "x ("+ str(winnerscore) + ") | "

                        # Getting all scores, to get the winner of the week
                        for player in list(self.channelweekshots[channel][week][i].keys()):
                            try:
                                weekscores[player] += self.channelweekshots[channel][week][i][player]
                            except:
                                weekscores[player] = self.channelweekshots[channel][week][i][player]
                             

                        if msgstring != "":
                            irc.reply("Shot scores for week " + str(week) + ": " + msgstring)
                            # Who's the winner at this point?
                            winnernick, winnerscore = max(iter(weekscores.items()), key=lambda k_v1:(k_v1[1],k_v1[0]))
                            irc.reply("Leader shooter: x%sx with %i points." % (winnernick, winnerscore)) 

                        else:
                            irc.reply("There aren't any week shot scores for this week yet.")
                    else:
                        # Showing the scores of <nick>
                        msgstring = ''
                        total = 0
                        for i in (1,2,3,4,5,6,7):
                            if self.channelweekshots[channel][week].get(i):
                                if self.channelweekshots[channel][week][i].get(nick):
                                    msgstring += self.dayname[i - 1] + ": "+ str(self.channelweekshots[channel][week][i].get(nick)) + " | "
                                    total += self.channelweekshots[channel][week][i].get(nick)

                        if msgstring != "":
                            irc.reply(nick + " shot scores for week " + str(self.woy) + ": " + msgstring)
                            irc.reply("Total: " + str(total) + " shot points.")
                        else:
                            irc.reply("There aren't any week shot scores for this nick.")


                else:
                    irc.reply("There aren't any week shot scores for this week yet.")
            else:
                irc.reply("There aren't any week shot scores for this channel yet.")
            
            if self.channelweeksaves.get(channel):
                if self.channelweeksaves[channel].get(week):
                    # Showing the winner for each day
                    if not nick:
                        msgstring = ''
                        # for each day of week
                        for i in (1,2,3,4,5,6,7):
                            if self.channelweeksaves[channel][week].get(i):
                                # Getting winner of the day
                                winnernick, winnerscore = max(iter(self.channelweeksaves[channel][week][i].items()), key=lambda k_v:(k_v[1],k_v[0]))
                                msgstring += self.dayname[i - 1] + ": x" + winnernick + "x ("+ str(winnerscore) + ") | "

                        # Getting all scores, to get the winner of the week
                        for player in list(self.channelweeksaves[channel][week][i].keys()):
                            try:
                                weekscores[player] += self.channelweeksaves[channel][week][i][player]
                            except:
                                weekscores[player] = self.channelweeksaves[channel][week][i][player]
                             

                        if msgstring != "":
                            irc.reply("Save scores for week " + str(week) + ": " + msgstring)
                            # Who's the winner at this point?
                            winnernick, winnerscore = max(iter(weekscores.items()), key=lambda k_v1:(k_v1[1],k_v1[0]))
                            irc.reply("Leader saver: x%sx with %i points." % (winnernick, winnerscore)) 

                        else:
                            irc.reply("There aren't any week save scores for this week yet.")
                    else:
                        # Showing the scores of <nick>
                        msgstring = ''
                        total = 0
                        for i in (1,2,3,4,5,6,7):
                            if self.channelweeksaves[channel][week].get(i):
                                if self.channelweeksaves[channel][week][i].get(nick):
                                    msgstring += self.dayname[i - 1] + ": "+ str(self.channelweeksaves[channel][week][i].get(nick)) + " | "
                                    total += self.channelweeksaves[channel][week][i].get(nick)

                        if msgstring != "":
                            irc.reply(nick + " save scores for week " + str(self.woy) + ": " + msgstring)
                            irc.reply("Total: " + str(total) + " save points.")
                        else:
                            irc.reply("There aren't any week save scores for this nick.")


                else:
                    irc.reply("There aren't any week save scores for this week yet.")
            else:
                irc.reply("There aren't any week save scores for this channel yet.")



        else:
            irc.reply("Are you sure this is a channel?")

    weekscores = wrap(weekscores, [optional('int'), optional('nick'), 'channel'])



    def listscores(self, irc, msg, args, size, channel):
        """
        [<size>] [<channel>]
        
        Shows the <size>-sized score list for <channel> (or for the current channel if no channel is given)
        """

        if irc.isChannel(channel):
            try:
                self.channelshootscores[channel]
            except:
                self.channelshootscores[channel] = {}

                try:
                self.channelsavescores[channel]
            except:
                self.channelsavescores[channel] = {}

            self._read_scores(channel)

            # How many results do we display?
            if (not size):
                listsize = self.toplist
            else:
                listsize = size

            # Sort the scores (reversed: the higher the better)
            shootscores = sorted(iter(self.channelshootscores[channel].items()), key=lambda k_v9:(k_v9[1],k_v9[0]), reverse=True)
            del shootscores[listsize:]

            # Sort the scores (reversed: the higher the better)
            savescores = sorted(iter(self.channelshootscores[channel].items()), key=lambda k_v9:(k_v9[1],k_v9[0]), reverse=True)
            del savescores[listsize:] 

            msgstring = ""
            for item in shootscores:
                # Why do we show the nicks as xnickx?
                # Just to prevent everyone that has ever played a hunt in the channel to be pinged every time anyone asks for the score list
                msgstring += "x" + item[0] + "x: "+ str(item[1]) + " | "
            if msgstring != "":
                irc.reply("\_o< ~ DuckHunt top-" + str(listsize) + " shoot scores for " + channel + " ~ >o_/")
                irc.reply(msgstring)
            else:
                irc.reply("There aren't any shoot scores for this channel yet.")
            
            for item in savescores:
                # Why do we show the nicks as xnickx?
                # Just to prevent everyone that has ever played a hunt in the channel to be pinged every time anyone asks for the score list
                msgstring += "x" + item[0] + "x: "+ str(item[1]) + " | "
            if msgstring != "":
                irc.reply("\_o< ~ DuckHunt top-" + str(listsize) + " save scores for " + channel + " ~ >o_/")
                irc.reply(msgstring)
            else:
                irc.reply("There aren't any save scores for this channel yet.")
        else:
            irc.reply("Are you sure this is a channel?")
    listscores = wrap(listscores, [optional('int'), 'channel'])


    def total(self, irc, msg, args, channel):
        """
        Shows the total amount of ducks shot or saved in <channel> (or in the current channel if no channel is given)
        """

        if irc.isChannel(channel):
            self._read_scores(channel)
            if (self.channelshootscores.get(channel)):
                scores = self.channelshootscores[channel]
                total = 0
                for player in list(scores.keys()):
                    total += scores[player]
                irc.reply(str(total) + " ducks have been shot in " + channel + "!")
            else:
                irc.reply("There are no scores for this channel yet")
            
            if (self.channelsavescores.get(channel)):
                scores = self.channelsavescores[channel]
                total = 0
                for player in list(scores.keys()):
                    total += scores[player]
                irc.reply(str(total) + " ducks have been saved in " + channel + "!")
            else:
                irc.reply("There are no save scores for this channel yet")
        else:
            irc.reply("Are you sure this is a channel?")
    total = wrap(total, ['channel'])


    def listtimes(self, irc, msg, args, size, channel):
        """
        [<size>] [<channel>]
        
        Shows the <size>-sized time list for <channel> (or for the current channel if no channel is given)
        """

        if irc.isChannel(channel):
            self._read_scores(channel)

            try:
                self.channeltimes[channel]
            except:
                self.channeltimes[channel] = {}

            try:
                self.channelworsttimes[channel]
            except:
                self.channelworsttimes[channel] = {}

            # How many results do we display?
            if (not size):
                listsize = self.toplist
            else:
                listsize = size

            # Sort the times (not reversed: the lower the better)
            times = sorted(iter(self.channeltimes[channel].items()), key=lambda k_v10:(k_v10[1],k_v10[0]), reverse=False)
            del times[listsize:] 

            msgstring = ""
            for item in times:
                # Same as in listscores for the xnickx
                msgstring += "x" + item[0] + "x: "+ str(round(item[1],2)) + " | "
                if msgstring != "":
                    irc.reply("\_o< ~ DuckHunt top-" + str(listsize) + " times for " + channel + " ~ >o_/")
                    irc.reply(msgstring)
            else:
                irc.reply("There aren't any best times for this channel yet.")


            times = sorted(iter(self.channelworsttimes[channel].items()), key=lambda k_v11:(k_v11[1],k_v11[0]), reverse=True)
            del times[listsize:] 

            msgstring = ""
            for item in times:
                # Same as in listscores for the xnickx
                #msgstring += "x" + item[0] + "x: "+ time.strftime('%H:%M:%S', time.gmtime(item[1])) + ", "
                roundseconds = round(item[1])
                delta = datetime.timedelta(seconds=roundseconds)
                msgstring += "x" + item[0] + "x: " + str(delta) + " | "
            if msgstring != "":
                irc.reply("\_o< ~ DuckHunt top-" + str(listsize) + " longest times for " + channel + " ~ >o_/")
                irc.reply(msgstring)
            else:
                irc.reply("There aren't any longest times for this channel yet.")


        else:
            irc.reply("Are you sure this is a channel?")
    listtimes = wrap(listtimes, [optional('int'), 'channel'])



    def dbg(self, irc, msg, args):
        """ 
        This is a debug command. If debug mode is not enabled, it won't do anything 
        """
        currentChannel = msg.args[0]
        if (self.debug):
            if irc.isChannel(currentChannel):
                self._launch(irc, msg, '')
    dbg = wrap(dbg)


    def bang(self, irc, msg, args):
        """
        Shoots the duck!
        """
        currentChannel = msg.args[0]

        if irc.isChannel(currentChannel):
            if(self.started.get(currentChannel) == True):

                # bangdelay: how much time between the duck was launched and this shot?
                if self.times[currentChannel]:
                    bangdelay = time.time() - self.times[currentChannel]
                else:
                    bangdelay = False


                # Is the player reloading?
                if (self.reloading[currentChannel].get(msg.nick) and time.time() - self.reloading[currentChannel][msg.nick] < self.reloadtime[currentChannel]):
                    irc.reply("%s, you are reloading... (Reloading takes %i seconds)" % (msg.nick, self.reloadtime[currentChannel]))
                    return 0
                

                # This player is now reloading
                self.reloading[currentChannel][msg.nick] = time.time();

                # There was a duck
                if (self.duck[currentChannel] == True):

                    # Did the player missed it?
                    if (random.random() < self.missprobability[currentChannel]):
                        irc.reply("%s, you missed the duck!" % (msg.nick))
                    else:

                        # Adds one point for the nick that shot the duck
                        try:
                            self.shootscores[currentChannel][msg.nick] += 1
                        except:
                            try:
                                self.shootscores[currentChannel][msg.nick] = 1
                            except:
                                self.shootscores[currentChannel] = {} 
                                self.shootscores[currentChannel][msg.nick] = 1

                        irc.reply("\_x< %s: %i shoot score (%.2f seconds)" % (msg.nick,  self.shootscores[currentChannel][msg.nick], bangdelay))

                        self.averagetime[currentChannel] += bangdelay

                        # Now save the bang delay for the player (if it's quicker than it's previous bangdelay)
                        try:
                            previoustime = self.toptimes[currentChannel][msg.nick]
                            if(bangdelay < previoustime):
                                self.toptimes[currentChannel][msg.nick] = bangdelay
                        except:
                            self.toptimes[currentChannel][msg.nick] = bangdelay


                        # Now save the bang delay for the player (if it's worst than it's previous bangdelay)
                        try:
                            previoustime = self.worsttimes[currentChannel][msg.nick]
                            if(bangdelay > previoustime):
                                self.worsttimes[currentChannel][msg.nick] = bangdelay
                        except:
                            self.worsttimes[currentChannel][msg.nick] = bangdelay


                        self.duck[currentChannel] = False

                        # Reset the basetime for the waiting time before the next duck
                        self.lastSpoke[currentChannel] = time.time()

                        if self.registryValue('ducks', currentChannel):
                            maxShoots = self.registryValue('ducks', currentChannel)
                        else:
                            maxShoots = 10

                        # End of Hunt
                        if (self.shoots[currentChannel]  == maxShoots):
                            self._end(irc, msg, args)

                            # If autorestart is enabled, we restart a hunt automatically!
                            if self.registryValue('autoRestart', currentChannel):
                                # This code shouldn't be here
                                self.started[currentChannel] = True
                                self._initthrottle(irc, msg, args, currentChannel)
                                if self.scores.get(currentChannel):
                                    self.scores[currentChannel] = {}
                                if self.reloading.get(currentChannel):
                                    self.reloading[currentChannel] = {}

                                self.averagetime[currentChannel] = 0


                # There was no duck or the duck has already been shot
                else:

                    # Removes one point for the nick that shot
                    try:
                        self.shootscores[currentChannel][msg.nick] -= 1
                    except:
                        try:
                            self.shootscores[currentChannel][msg.nick] = -1
                        except:
                            self.shootscores[currentChannel] = {} 
                            self.shootscores[currentChannel][msg.nick] = -1

                    # Base message
                    message = 'There was no duck!'

                    # Adding additional message if kick
                    if self.registryValue('kickMode', currentChannel) and irc.nick in irc.state.channels[currentChannel].ops:
                        message += ' You just shot yourself!'

                    # Adding nick and score
                    message += " %s: %i shoot score" % (msg.nick, self.shootscores[currentChannel][msg.nick])

                    # If we were able to have a bangdelay (ie: a duck was launched before someone did bang)
                    if (bangdelay):
                        # Adding time
                        message += " (" + str(round(bangdelay,2)) + " seconds)"

                    # If kickMode is enabled for this channel, and the bot have op capability, let's kick!
                    if self.registryValue('kickMode', currentChannel) and irc.nick in irc.state.channels[currentChannel].ops:
                        irc.queueMsg(ircmsgs.kick(currentChannel, msg.nick, message))
                    else:
                        # Else, just say it
                        irc.reply(message)


            else:
                irc.reply("There is no hunt right now! You can start a hunt with the 'start' command")
        else:
            irc.error('You have to be on a channel')

    bang = wrap(bang)

    def bef(self, irc, msg, args):
        """
        Befriends (saves) the duck!
        """
        currentChannel = msg.args[0]

        if irc.isChannel(currentChannel):
            if(self.started.get(currentChannel) == True):

                # bangdelay: how much time between the duck was launched and this save?
                if self.times[currentChannel]:
                    bangdelay = time.time() - self.times[currentChannel]
                else:
                    bangdelay = False


                # Is the player reloading?
                if (self.reloading[currentChannel].get(msg.nick) and time.time() - self.reloading[currentChannel][msg.nick] < self.reloadtime[currentChannel]):
                    irc.reply("%s, you are preparing to befriend... (preparing to befriend takes %i seconds)" % (msg.nick, self.reloadtime[currentChannel]))
                    return 0
                

                # This player is now reloading
                self.reloading[currentChannel][msg.nick] = time.time();

                # There was a duck
                if (self.duck[currentChannel] == True):

                    # Did the player missed it?
                    if (random.random() < self.missprobability[currentChannel]):
                        irc.reply("%s, you missed befriending the duck!" % (msg.nick))
                    else:

                        # Adds one point for the nick that befriended the duck
                        try:
                            self.savescores[currentChannel][msg.nick] += 1
                        except:
                            try:
                                self.savescores[currentChannel][msg.nick] = 1
                            except:
                                self.savescores[currentChannel] = {} 
                                self.savescores[currentChannel][msg.nick] = 1

                        irc.reply("\_O< %s: %i save points (%.2f seconds)" % (msg.nick,  self.savescores[currentChannel][msg.nick], bangdelay))

                        self.averagetime[currentChannel] += bangdelay

                        # Now save the bang delay for the player (if it's quicker than it's previous bangdelay)
                        try:
                            previoustime = self.toptimes[currentChannel][msg.nick]
                            if(bangdelay < previoustime):
                                self.toptimes[currentChannel][msg.nick] = bangdelay
                        except:
                            self.toptimes[currentChannel][msg.nick] = bangdelay


                        # Now save the bang delay for the player (if it's worst than it's previous bangdelay)
                        try:
                            previoustime = self.worsttimes[currentChannel][msg.nick]
                            if(bangdelay > previoustime):
                                self.worsttimes[currentChannel][msg.nick] = bangdelay
                        except:
                            self.worsttimes[currentChannel][msg.nick] = bangdelay


                        self.duck[currentChannel] = False

                        # Reset the basetime for the waiting time before the next duck
                        self.lastSpoke[currentChannel] = time.time()

                        if self.registryValue('ducks', currentChannel):
                            maxShoots = self.registryValue('ducks', currentChannel)
                        else:
                            maxShoots = 10

                        # End of Hunt
                        if (self.shoots[currentChannel]  == maxShoots):
                            self._end(irc, msg, args)

                            # If autorestart is enabled, we restart a hunt automatically!
                            if self.registryValue('autoRestart', currentChannel):
                                # This code shouldn't be here
                                self.started[currentChannel] = True
                                self._initthrottle(irc, msg, args, currentChannel)
                                if self.scores.get(currentChannel):
                                    self.scores[currentChannel] = {}
                                if self.reloading.get(currentChannel):
                                    self.reloading[currentChannel] = {}

                                self.averagetime[currentChannel] = 0


                # There was no duck or the duck has already been shot or saved!
                else:

                    # Removes one point for the nick that tried to save
                    try:
                        self.savescores[currentChannel][msg.nick] -= 1
                    except:
                        try:
                            self.savescores[currentChannel][msg.nick] -= 1
                        except:
                            self.savescores[currentChannel] = {} 
                            self.savescores[currentChannel][msg.nick] = -1

                    # Base message
                    message = 'There was no duck!'

                    # Adding additional message if kick
                    if self.registryValue('kickMode', currentChannel) and irc.nick in irc.state.channels[currentChannel].ops:
                        message += ' You just befriended yourself!'

                    # Adding nick and score
                    message += " %s: %i" % (msg.nick, self.scores[currentChannel][msg.nick])

                    # If we were able to have a bangdelay (ie: a duck was launched before someone did bang)
                    if (bangdelay):
                        # Adding time
                        message += " (" + str(round(bangdelay,2)) + " seconds)"

                    # If kickMode is enabled for this channel, and the bot have op capability, let's kick!
                    if self.registryValue('kickMode', currentChannel) and irc.nick in irc.state.channels[currentChannel].ops:
                        irc.queueMsg(ircmsgs.kick(currentChannel, msg.nick, message))
                    else:
                        # Else, just say it
                        irc.reply(message)


            else:
                irc.reply("There is no hunt right now! You can start a hunt with the 'start' command")
        else:
            irc.error('You have to be on a channel')

    bef = wrap(bef)


    def doPrivmsg(self, irc, msg):
        currentChannel = msg.args[0]
        if irc.isChannel(msg.args[0]):
            if (msg.args[1] == '\_o< quack!'):
                message = msg.nick + ", don't pretend to be me!";
                # If kickMode is enabled for this channel, and the bot have op capability, let's kick!
                if self.registryValue('kickMode', currentChannel) and irc.nick in irc.state.channels[currentChannel].ops:
                    irc.queueMsg(ircmsgs.kick(currentChannel, msg.nick, message))
                else:
                    # Else, just say it
                    irc.reply(message)



    def _end(self, irc, msg, args):
        """ 
        End of the hunt (is called when the hunts stop "naturally" or when someone uses the !stop command)
        """

        currentChannel = msg.args[0]

        # End the hunt
        self.started[currentChannel] = False

        try:
            self.channelshootscores[currentChannel]
        except:
            self.channelshootscores[currentChannel] = {}

        try:
            self.channelsavescores[currentChannel]
        except:
            self.channelsavescores[currentChannel] = {}

        if not self.registryValue('autoRestart', currentChannel):
            irc.reply("The hunt stops now!")

        # Showing scores
        if (self.shootscores.get(currentChannel)):

            # Getting shooter winner
            shooterwinnernick, shooterwinnerscore = max(iter(self.shootscores.get(currentChannel).items()), key=lambda k_v12:(k_v12[1],k_v12[0]))
            if self.registryValue('ducks', currentChannel):
                maxShoots = self.registryValue('ducks', currentChannel)
            else:
                maxShoots = 10

            # Is there a perfect?
            if (shooterwinnerscore == maxShoots):
                irc.reply("\o/ %s: %i ducks shot out of %i: perfect!!! +%i \o/" % (shooterwinnernick, shooterwinnerscore, maxShoots, self.perfectbonus))
                self.shootscores[currentChannel][shooterwinnernick] += self.perfectbonus
            else:
                # Showing scores
                #irc.reply("Winner: %s with %i points" % (winnernick, winnerscore))
                #irc.reply(self.scores.get(currentChannel))
                #TODO: Better display
                irc.reply(sorted(iter(self.shootscores.get(currentChannel).items()), key=lambda k_v4:(k_v4[1],k_v4[0]), reverse=True))
        else:
            irc.reply("Not a single duck was shot during this hunt!")

        # Showing saves
        if (self.savescores.get(currentChannel)):

            # Getting save winner
            savewinnernick, savewinnerscore = max(iter(self.savescores.get(currentChannel).items()), key=lambda k_v12:(k_v12[1],k_v12[0]))
            if self.registryValue('ducks', currentChannel):
                maxShoots = self.registryValue('ducks', currentChannel)
            else:
                maxShoots = 10

            # Is there a perfect?
            if (savewinnerscore == maxShoots):
                irc.reply("\o/ %s: %i ducks saved out of %i: perfect!!! +%i \o/" % (savewinnernick, savewinnerscore, maxShoots, self.perfectbonus))
                self.savescores[currentChannel][winnernick] += self.perfectbonus
            else:
                # Showing scores
                #irc.reply("Winner: %s with %i points" % (winnernick, winnerscore))
                #irc.reply(self.scores.get(currentChannel))
                #TODO: Better display
                irc.reply(sorted(iter(self.savescores.get(currentChannel).items()), key=lambda k_v4:(k_v4[1],k_v4[0]), reverse=True))
        else:
            irc.reply("Not a single duck was saved during this hunt!")

        if (self.shootscores.get(currentChannel) or self.savescores.get(currentChannel))
            # Getting channel best time (to see if the best time of this hunt is better)
            channelbestnick = None
            channelbesttime = None
            if self.channeltimes.get(currentChannel):
                channelbestnick, channelbesttime = min(iter(self.channeltimes.get(currentChannel).items()), key=lambda k_v5:(k_v5[1],k_v5[0]))

            # Showing best time
            recordmsg = ''
            if (self.toptimes.get(currentChannel)):
                key,value = min(iter(self.toptimes.get(currentChannel).items()), key=lambda k_v6:(k_v6[1],k_v6[0]))
            if (channelbesttime and value < channelbesttime):
                recordmsg = '. This is the new record for this channel! (previous record was held by ' + channelbestnick + ' with ' + str(round(channelbesttime,2)) +  ' seconds)'
            else:
                try:
                    if(value < self.channeltimes[currentChannel][key]):
                        recordmsg = ' (this is your new record in this channel! Your previous record was ' + str(round(self.channeltimes[currentChannel][key],2)) + ')'
                except:
                    recordmsg = ''

            irc.reply("Best time: %s with %.2f seconds%s" % (key, value, recordmsg))

            # Getting channel worst time (to see if the worst time of this hunt is worst)
            channelworstnick = None
            channelworsttime = None
            if self.channelworsttimes.get(currentChannel):
                channelworstnick, channelworsttime = max(iter(self.channelworsttimes.get(currentChannel).items()), key=lambda k_v7:(k_v7[1],k_v7[0]))

            # Showing worst time
            recordmsg = ''
            if (self.worsttimes.get(currentChannel)):
                key,value = max(iter(self.worsttimes.get(currentChannel).items()), key=lambda k_v8:(k_v8[1],k_v8[0]))
            if (channelworsttime and value > channelworsttime):
                recordmsg = '. This is the new longest time for this channel! (previous longest time was held by ' + channelworstnick + ' with ' + str(round(channelworsttime,2)) +  ' seconds)'
            else:
                try:
                    if(value > self.channelworsttimes[currentChannel][key]):
                        recordmsg = ' (this is your new longest time in this channel! Your previous longest time was ' + str(round(self.channelworsttimes[currentChannel][key],2)) + ')'
                except:
                    recordmsg = ''

            # Only display worst time if something new
            if (recordmsg != ''):
                irc.reply("Longest time: %s with %.2f seconds%s" % (key, value, recordmsg))

            # Showing average shooting time:
            #if (self.shoots[currentChannel] > 1):
            #irc.reply("Average shooting time: %.2f seconds" % ((self.averagetime[currentChannel] / self.shoots[currentChannel])))

            # Write the scores and times to disk
            self._calc_scores(currentChannel)
            self._write_scores(currentChannel)

            # Did someone took the lead shooting?
            weekscores = {}
            if self.channelweekshots.get(currentChannel):
                if self.channelweekshots[currentChannel].get(self.woy):
                    msgstring = ''
                    # for each day of week
                    for i in (1,2,3,4,5,6,7):
                        if self.channelweekshots[currentChannel][self.woy].get(i):
                            # Getting all scores, to get the winner of the week
                            for player in list(self.channelweekshots[currentChannel][self.woy][i].keys()):
                                try:
                                    weekscores[player] += self.channelweekshots[currentChannel][self.woy][i][player]
                                except:
                                    weekscores[player] = self.channelweekshots[currentChannel][self.woy][i][player]

                            winnernick, winnerscore = max(iter(weekscores.items()), key=lambda k_v3:(k_v3[1],k_v3[0]))
                            if (winnernick != self.leadershooter[currentChannel]):
                                if self.leadershooter[currentChannel] != None:
                                    irc.reply("%s took the lead for the week over %s with %i shot points." % (winnernick, self.leadershooter[currentChannel], winnerscore)) 
                                else:
                                    irc.reply("%s has the lead for the week with %i shot points." % (winnernick, winnerscore)) 
                                self.leadershooter[currentChannel] = winnernick

            # Did someone took the lead saving?
            weekscores = {}
            if self.channelweeksaves.get(currentChannel):
                if self.channelweeksaves[currentChannel].get(self.woy):
                    msgstring = ''
                    # for each day of week
                    for i in (1,2,3,4,5,6,7):
                        if self.channelweeksaves[currentChannel][self.woy].get(i):
                            # Getting all scores, to get the winner of the week
                            for player in list(self.channelweeksaves[currentChannel][self.woy][i].keys()):
                                try:
                                    weekscores[player] += self.channelweeksaves[currentChannel][self.woy][i][player]
                                except:
                                    weekscores[player] = self.channelweeksaves[currentChannel][self.woy][i][player]

                            winnernick, winnerscore = max(iter(weekscores.items()), key=lambda k_v3:(k_v3[1],k_v3[0]))
                            if (winnernick != self.leadersaver[currentChannel]):
                                if self.leadersaver[currentChannel] != None:
                                    irc.reply("%s took the lead for the week over %s with %i save points." % (winnernick, self.leadersaver[currentChannel], winnerscore)) 
                                else:
                                    irc.reply("%s has the lead for the week with %i save points." % (winnernick, winnerscore)) 
                                self.leadersaver[currentChannel] = winnernick


        # Reinit current hunt scores
        if self.shootscores.get(currentChannel):
            self.shootscores[currentChannel] = {}

        if self.savescores.get(currentChannel):
            self.savescores[currentChannel] = {}

        # Reinit current hunt times
        if self.toptimes.get(currentChannel):
            self.toptimes[currentChannel] = {}
        if self.worsttimes.get(currentChannel):
            self.worsttimes[currentChannel] = {}

        # No duck lauched
        self.duck[currentChannel] = False

        # Reinit number of shoots
        self.shoots[currentChannel] = 0

    def _launch(self, irc, msg, args):
        """
        Launch a duck
        """
        currentChannel = msg.args[0]
        if irc.isChannel(currentChannel):
            if(self.started[currentChannel] == True):
                if (self.duck[currentChannel] == False):

                    # Store the time when the duck has been launched
                    self.times[currentChannel] = time.time()

                    # Store the fact that there's a duck now
                    self.duck[currentChannel] = True

                    # Send message directly (instead of queuing it with irc.reply)
                    irc.sendMsg(ircmsgs.privmsg(currentChannel, "\_o< quack!"))

                    # Define a new throttle[currentChannel] for the next launch
                    self.throttle[currentChannel] = random.randint(self.minthrottle[currentChannel], self.maxthrottle[currentChannel])

                    try:
                        self.shoots[currentChannel] += 1
                    except:
                        self.shoots[currentChannel] = 1
                else:

                    irc.reply("Already a duck")
            else:
                irc.reply("The hunt has not started yet!")
        else:
            irc.error('You have to be on a channel')


Class = DuckHunt

# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:
