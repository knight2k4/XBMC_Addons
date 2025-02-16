#   Copyright (C) 2015 Jason Anderson, Kevin S. Graer
#
#
# This file is part of PseudoTV Live.
#
# PseudoTV is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# PseudoTV is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with PseudoTV.  If not, see <http://www.gnu.org/licenses/>.

import xbmc, xbmcgui, xbmcaddon, xbmcvfs
import os, sys, re
import time, datetime, threading, _strptime, calendar
import httplib, urllib, urllib2, feedparser, socket, json
import base64, shutil, random, errno


from parsers import xmltv
from utils import *
from urllib import unquote
from urllib import urlopen
from xml.etree import ElementTree as ET
from xml.dom.minidom import parse, parseString
from subprocess import Popen, PIPE, STDOUT
from Playlist import Playlist
from Globals import *
from Channel import Channel
from VideoParser import VideoParser
from FileAccess import FileAccess
from hdhr import hdhr
from apis import tvdb_api, tmdb_api
from apis import sickbeard
from apis import couchpotato
from apis import tvdb
from apis import tmdb
from urllib2 import urlopen
from urllib2 import HTTPError, URLError
from datetime import date
from datetime import timedelta

socket.setdefaulttimeout(30)

# Commoncache plugin import
try:
    import StorageServer
except Exception,e:
    import storageserverdummy as StorageServer
        
try:
    from Donor import *     
    DonorDel()
    xbmc.log("script.pseudotv.live-ChannelList: Donor Imported")
except Exception,e:
    DonorDel(True)
    xbmc.log("script.pseudotv.live-ChannelList: Donor Import Failed, Disabling Donor Features " + str(e))

try:
    from metahandler import metahandlers
except Exception,e:  
    xbmc.log("script.pseudotv.live-ChannelList: metahandler Import Failed" + str(e))    

class ChannelList:
    def __init__(self):
        self.networkList = []
        self.studioList = []
        self.mixedGenreList = []
        self.showGenreList = []
        self.movieGenreList = []
        self.movie3Dlist = []
        self.musicGenreList = []
        self.pluginPathList = []
        self.pluginNameList = []
        self.showList = []
        self.channels = []
        self.cached_json_detailed_TV = []
        self.cached_json_detailed_Movie = []
        self.cached_json_detailed_trailers = []  
        self.cached_json_detailed_xmltvChannels_pvr = []
        self.cached_readXMLTV = []
        self.videoParser = VideoParser()
        self.autoplaynextitem = False
        self.sleepTime = 0
        self.threadPaused = False
        self.runningActionChannel = 0
        self.runningActionId = 0
        self.enteredChannelCount = 0
        self.background = True
        self.youtube_ok = self.youtube_player()
        self.log('Youtube Player is ' + str(self.youtube_ok))
        self.Enable_FindLogo = REAL_SETTINGS.getSetting('Enable_FindLogo') == "true"
        
        try:
            self.limit = MEDIA_LIMIT[int(REAL_SETTINGS.getSetting('MEDIA_LIMIT'))]
        except:
            self.limit = 25
            self.log('Channel Media Limit Failed!')
        self.log('Channel Media Limit is ' + str(self.limit))
        
        random.seed() 

        
    def readConfig(self):
        self.ResetChanLST = list(REAL_SETTINGS.getSetting('ResetChanLST'))
        self.log('Channel Reset List is ' + str(self.ResetChanLST))
        self.channelResetSetting = int(REAL_SETTINGS.getSetting("ChannelResetSetting"))
        self.log('Channel Reset Setting is ' + str(self.channelResetSetting))
        self.forceReset = REAL_SETTINGS.getSetting('ForceChannelReset') == "true"
        self.log('Force Reset is ' + str(self.forceReset))
        self.updateDialog = xbmcgui.DialogProgress()
        self.startMode = int(REAL_SETTINGS.getSetting("StartMode"))
        self.log('Start Mode is ' + str(self.startMode))
        self.backgroundUpdating = int(REAL_SETTINGS.getSetting("ThreadMode"))
        self.inc3D = REAL_SETTINGS.getSetting('Include3D') == "true"
        self.log("Include 3D is " + str(self.inc3D))
        self.incIceLibrary = REAL_SETTINGS.getSetting('IncludeIceLib') == "true"
        self.log("IceLibrary is " + str(self.incIceLibrary))
        self.incBCTs = REAL_SETTINGS.getSetting('IncludeBCTs') == "true"
        self.log("IncludeBCTs is " + str(self.incBCTs))
        self.t = tvdb_api.Tvdb()
        self.tvdbAPI = tvdb.TVDB(TVDB_API_KEY)
        self.tmdbAPI = tmdb.TMDB(TMDB_API_KEY)  
        self.sbAPI = sickbeard.SickBeard(REAL_SETTINGS.getSetting('sickbeard.baseurl'),REAL_SETTINGS.getSetting('sickbeard.apikey'))
        self.cpAPI = couchpotato.CouchPotato(REAL_SETTINGS.getSetting('couchpotato.baseurl'),REAL_SETTINGS.getSetting('couchpotato.apikey'))
        self.OSpath = self.getOSPpath(REAL_SETTINGS.getSetting('os'))
        self.findMaxChannels()
        
        if self.forceReset:
            REAL_SETTINGS.setSetting("INTRO_PLAYED","false")
            REAL_SETTINGS.setSetting('StartupMessage', 'false')    
            REAL_SETTINGS.setSetting('ForceChannelReset', 'false')
            self.forceReset = False

        try:
            self.lastResetTime = int(ADDON_SETTINGS.getSetting("LastResetTime"))
        except Exception,e:
            self.lastResetTime = 0

        try:
            self.lastExitTime = int(ADDON_SETTINGS.getSetting("LastExitTime"))
        except Exception,e:
            self.lastExitTime = int(time.time())
            
            
    def setupList(self, silent=False):
        self.log("setupList")
        self.readConfig()
        if not silent:
            self.updateDialog.create("PseudoTV Live", "Updating channel list")
            self.updateDialog.update(0, "Updating channel list", "")
            self.updateDialogProgress = 0
        foundvalid = False
        makenewlists = False
        
        if not silent:
            self.background = False
        else:
            self.background = True
        
        if self.backgroundUpdating > 0 and self.myOverlay.isMaster == True:
            makenewlists = True
            
        # Go through all channels, create their arrays, and setup the new playlist
        for i in range(self.maxChannels):
            if not silent:
                self.updateDialogProgress = i * 100 // self.enteredChannelCount
                self.updateDialog.update(self.updateDialogProgress, "Loading channel " + str(i + 1), "waiting for file lock")
            self.channels.append(Channel())
            
            if not silent:
                # If the user pressed cancel, stop everything and exit
                if self.updateDialog.iscanceled():
                    self.log('Update channels cancelled')
                    self.updateDialog.close()
                    return None
                
            self.setupChannel(i + 1, self.background, makenewlists, False)
            
            if self.channels[i].isValid:
                foundvalid = True

        if makenewlists == True:
            REAL_SETTINGS.setSetting('ForceChannelReset', 'false')

        if foundvalid == False and makenewlists == False:
            for i in range(self.maxChannels):
                if not silent:
                    self.updateDialogProgress = i * 100 // self.enteredChannelCount
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(i + 1), "waiting for file lock")
                self.setupChannel(i + 1, self.background, True, False)

                if self.channels[i].isValid:
                    foundvalid = True
                    break
        
        if not silent:
            self.updateDialog.update(100, "Update complete", "")
            self.updateDialog.close()
        return self.channels 

        
    def log(self, msg, level = xbmc.LOGDEBUG):
        log('ChannelList: ' + msg, level)

    
    def logDebug(self, msg, level = xbmc.LOGDEBUG):
        if DEBUG == 'true':
            log('ChannelList: ' + msg, level)
            
            
    # Determine the maximum number of channels by opening consecutive
    # playlists until we don't find one
    def findMaxChannels(self):
        self.log('findMaxChannels')
        self.maxChannels = 0
        self.enteredChannelCount = 0

        for i in range(999):
            chtype = 9999
            chsetting1 = ''
            chsetting2 = ''
            chsetting3 = ''
            chsetting4 = ''
            
            try:
                chtype = int(ADDON_SETTINGS.getSetting('Channel_' + str(i + 1) + '_type'))
                chsetting1 = ADDON_SETTINGS.getSetting('Channel_' + str(i + 1) + '_1')
                chsetting2 = ADDON_SETTINGS.getSetting('Channel_' + str(i + 1) + '_2')
                chsetting3 = ADDON_SETTINGS.getSetting('Channel_' + str(i + 1) + '_3')
                chsetting4 = ADDON_SETTINGS.getSetting('Channel_' + str(i + 1) + '_4')
            except Exception,e:
                pass

            if chtype == 0:
                if FileAccess.exists(xbmc.translatePath(chsetting1)):
                    self.maxChannels = i + 1
                    self.enteredChannelCount += 1
            elif chtype <= 20:
                if len(chsetting1) > 0:
                    self.maxChannels = i + 1
                    self.enteredChannelCount += 1
                    
            if self.forceReset and (chtype != 9999):
                ADDON_SETTINGS.setSetting('Channel_' + str(i + 1) + '_changed', "True")

            if self.Enable_FindLogo == True:
                if self.background == False:
                    self.myOverlay.background.setLabel('Searching for Channel logos (' + str((i + 1)/10) + '%)')

                if chtype not in [6,7,9999]:
                    if chtype <= 7 or chtype == 12:
                        chname = self.getChannelName(chtype, chsetting1)
                    else:
                        chname = self.getChannelName(chtype, (i + 1))
                    FindLogo(chtype, chname)
                    
        if self.background == False:
            self.myOverlay.background.setLabel('Initializing') 
            
        self.log('findMaxChannels return ' + str(self.maxChannels))


    # Code for sending JSON through http adapted from code by sffjunkie (forum.xbmc.org/showthread.php?t=92196)
    def sendJSON(self, command):
        self.log('sendJSON')
        data = ''
        try:
            data = xbmc.executeJSONRPC(uni(command))
        except UnicodeEncodeError:
            data = xbmc.executeJSONRPC(ascii(command))
        return uni(data)
        
     
    def setupChannel(self, channel, background = False, makenewlist = False, append = False):
        self.log('setupChannel ' + str(channel))
        returnval = False
        createlist = makenewlist
        chtype = 9999
        chsetting1 = ''
        chsetting2 = ''
        chsetting3 = ''
        chsetting4 = ''
        needsreset = False
        self.background = background
        self.settingChannel = channel

        try:
            chtype = int(ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_type'))
            chsetting1 = ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_1')
            chsetting2 = ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_2')
            chsetting3 = ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_3')
            chsetting4 = ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_4')
        except:
            pass

        while len(self.channels) < channel:
            self.channels.append(Channel())

        if chtype == 9999:
            self.channels[channel - 1].isValid = False
            return False

        self.channels[channel - 1].type = chtype
        self.channels[channel - 1].isSetup = True
        self.channels[channel - 1].loadRules(channel)
        self.runActions(RULES_ACTION_START, channel, self.channels[channel - 1])

        try:
            needsreset = ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_changed') == 'True'
            
            # force rebuild
            if chtype == 8:
                self.log("Force LiveTV rebuild")
                needsreset = True

            if needsreset:
                self.channels[channel - 1].isSetup = False
        except:
            pass

        # If possible, use an existing playlist
        # Don't do this if we're appending an existing channel
        # Don't load if we need to reset anyway
        if FileAccess.exists(CHANNELS_LOC + 'channel_' + str(channel) + '.m3u') and append == False and needsreset == False:
            try:
                self.channels[channel - 1].totalTimePlayed = int(ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_time', True))
                createlist = True

                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Loading channel " + str(channel), "reading playlist")

                if self.channels[channel - 1].setPlaylist(CHANNELS_LOC + 'channel_' + str(channel) + '.m3u') == True:
                    self.channels[channel - 1].isValid = True
                    self.channels[channel - 1].fileName = CHANNELS_LOC + 'channel_' + str(channel) + '.m3u'
                    returnval = True

                    # If this channel has been watched for longer than it lasts, reset the channel
                    if self.channelResetSetting == 0 and self.channels[channel - 1].totalTimePlayed < self.channels[channel - 1].getTotalDuration():
                        createlist = False

                    if self.channelResetSetting > 0 and self.channelResetSetting < 4:
                        timedif = time.time() - self.lastResetTime

                        if self.channelResetSetting == 1 and timedif < (60 * 60 * 24):
                            createlist = False

                        if self.channelResetSetting == 2 and timedif < (60 * 60 * 24 * 7):
                            createlist = False

                        if self.channelResetSetting == 3 and timedif < (60 * 60 * 24 * 30):
                            createlist = False

                        if timedif < 0:
                            createlist = False

                    if self.channelResetSetting == 4:
                        createlist = False
            except:
                pass

        if createlist or needsreset:
            self.channels[channel - 1].isValid = False

            if makenewlist:
                try:
                    xbmcvfs.delete(CHANNELS_LOC + 'channel_' + str(channel) + '.m3u')
                except:
                    self.log("Unable to delete " + 'channel_' + str(channel) + '.m3u', xbmc.LOGERROR)
                append = False

                if createlist:
                    ADDON_SETTINGS.setSetting('LastResetTime', str(int(time.time())))

        if append == False:
            if chtype == 6 and chsetting2 == str(MODE_ORDERAIRDATE):
                self.channels[channel - 1].mode = MODE_ORDERAIRDATE

            # if there is no start mode in the channel mode flags, set it to the default
            if self.channels[channel - 1].mode & MODE_STARTMODES == 0:
                if self.startMode == 0:
                    self.channels[channel - 1].mode |= MODE_RESUME
                elif self.startMode == 1:
                    self.channels[channel - 1].mode |= MODE_REALTIME
                elif self.startMode == 2:
                    self.channels[channel - 1].mode |= MODE_RANDOM

        if ((createlist or needsreset) and makenewlist) or append:
            if self.background == False:
                self.updateDialogProgress = (channel - 1) * 100 // self.enteredChannelCount
                self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "")

            if self.makeChannelList(channel, chtype, chsetting1, chsetting2, chsetting3, chsetting4, append) == True:
                if self.channels[channel - 1].setPlaylist(CHANNELS_LOC + 'channel_' + str(channel) + '.m3u') == True:
                    returnval = True
                    self.channels[channel - 1].fileName = CHANNELS_LOC + 'channel_' + str(channel) + '.m3u'
                    self.channels[channel - 1].isValid = True
                    
                    # Don't reset variables on an appending channel
                    if append == False:
                        self.channels[channel - 1].totalTimePlayed = 0
                        ADDON_SETTINGS.setSetting('Channel_' + str(channel) + '_time', '0')

                        if needsreset:
                            if channel not in self.ResetChanLST:
                                ADDON_SETTINGS.setSetting('Channel_' + str(channel) + '_changed', 'False')
                            REAL_SETTINGS.setSetting('ResetChanLST', '')
                            self.channels[channel - 1].isSetup = True
                    
        self.runActions(RULES_ACTION_BEFORE_CLEAR, channel, self.channels[channel - 1])

        # Don't clear history when appending channels
        if self.background == False and append == False and self.myOverlay.isMaster:
            self.updateDialogProgress = (channel - 1) * 100 // self.enteredChannelCount
            self.updateDialog.update(self.updateDialogProgress, "Loading channel " + str(channel), "clearing history")
            self.clearPlaylistHistory(channel)

        if append == False:
            self.runActions(RULES_ACTION_BEFORE_TIME, channel, self.channels[channel - 1])

            if self.channels[channel - 1].mode & MODE_ALWAYSPAUSE > 0:
                self.channels[channel - 1].isPaused = True

            if self.channels[channel - 1].mode & MODE_RANDOM > 0:
                self.channels[channel - 1].showTimeOffset = random.randint(0, self.channels[channel - 1].getTotalDuration())

            if self.channels[channel - 1].mode & MODE_REALTIME > 0:
                timedif = int(self.myOverlay.timeStarted) - self.lastExitTime
                self.channels[channel - 1].totalTimePlayed += timedif

            if self.channels[channel - 1].mode & MODE_RESUME > 0:
                self.channels[channel - 1].showTimeOffset = self.channels[channel - 1].totalTimePlayed
                self.channels[channel - 1].totalTimePlayed = 0

            while self.channels[channel - 1].showTimeOffset > self.channels[channel - 1].getCurrentDuration():
                self.channels[channel - 1].showTimeOffset -= self.channels[channel - 1].getCurrentDuration()
                self.channels[channel - 1].addShowPosition(1)

        self.channels[channel - 1].name = self.getChannelName(chtype, chsetting1)

        if ((createlist or needsreset) and makenewlist) and returnval:
            self.runActions(RULES_ACTION_FINAL_MADE, channel, self.channels[channel - 1])
        else:
            self.runActions(RULES_ACTION_FINAL_LOADED, channel, self.channels[channel - 1])
        return returnval

        
    def clearPlaylistHistory(self, channel):
        self.log("clearPlaylistHistory")

        if self.channels[channel - 1].isValid == False:
            self.log("channel not valid, ignoring")
            return

        # if we actually need to clear anything
        if self.channels[channel - 1].totalTimePlayed > (60 * 60 * 24 * 2):
            try:
                fle = FileAccess.open(CHANNELS_LOC + 'channel_' + str(channel) + '.m3u', 'w')
            except:
                self.log("clearPlaylistHistory Unable to open the smart playlist", xbmc.LOGERROR)
                return

            flewrite = uni("#EXTM3U\n")
            tottime = 0
            timeremoved = 0

            for i in range(self.channels[channel - 1].Playlist.size()):
                tottime += self.channels[channel - 1].getItemDuration(i)

                if tottime > (self.channels[channel - 1].totalTimePlayed - (60 * 60 * 12)):
                    tmpstr = str(self.channels[channel - 1].getItemDuration(i)) + ','
                    tmpstr += self.channels[channel - 1].getItemTitle(i) + "//" + self.channels[channel - 1].getItemEpisodeTitle(i) + "//" + self.channels[channel - 1].getItemDescription(i) + "//" + self.channels[channel - 1].getItemgenre(i) + "//" + self.channels[channel - 1].getItemtimestamp(i) + "//" + self.channels[channel - 1].getItemLiveID(i)
                    tmpstr = uni(tmpstr[:2036])
                    tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                    tmpstr = uni(tmpstr) + uni('\n') + uni(self.channels[channel - 1].getItemFilename(i))
                    flewrite += uni("#EXTINF:") + uni(tmpstr) + uni("\n")
                else:
                    timeremoved = tottime

            fle.write(flewrite)
            fle.close()

            if timeremoved > 0:
                if self.channels[channel - 1].setPlaylist(CHANNELS_LOC + 'channel_' + str(channel) + '.m3u') == False:
                    self.channels[channel - 1].isValid = False
                else:
                    self.channels[channel - 1].totalTimePlayed -= timeremoved
                    # Write this now so anything sharing the playlists will get the proper info
                    ADDON_SETTINGS.setSetting('Channel_' + str(channel) + '_time', str(self.channels[channel - 1].totalTimePlayed))


    def getChannelName(self, chtype, setting1):
        chname = ''
        if chtype <= 7 or chtype == 12:
            if len(setting1) == 0:
                return ''
            elif chtype == 0:
                return self.getSmartPlaylistName(setting1)
            elif chtype == 1 or chtype == 2 or chtype == 5 or chtype == 6 or chtype == 12:
                return setting1
            elif chtype == 3:
                return setting1 + " TV"
            elif chtype == 4:
                return setting1 + " Movies"
            elif chtype == 12:
                return setting1 + " Music"
            elif chtype == 7:
                if setting1[-1] == '/' or setting1[-1] == '\\':
                    return os.path.split(setting1[:-1])[1]
                else:
                    return os.path.split(setting1)[1]
        else:
            #setting1 == channel number
            chname = ADDON_SETTINGS.getSetting("Channel_" + str(setting1) + "_rule_1_opt_1")
            if len(chname) != 0:
                return chname
        return ''


    # Open the smart playlist and read the name out of it...this is the channel name
    def getSmartPlaylistName(self, fle):
        self.log('getSmartPlaylistName')
        fle = xbmc.translatePath(fle)

        try:
            xml = FileAccess.open(fle, "r")
        except:
            self.log("getSmartPlaylistName Unable to open the smart playlist " + fle, xbmc.LOGERROR)
            return ''

        try:
            dom = parse(xml)
        except:
            self.log('getSmartPlaylistName Problem parsing playlist ' + fle, xbmc.LOGERROR)
            xml.close()
            return ''

        xml.close()

        try:
            plname = dom.getElementsByTagName('name')
            self.log('getSmartPlaylistName return ' + plname[0].childNodes[0].nodeValue)
            return plname[0].childNodes[0].nodeValue
        except:
            self.log("Unable to get the playlist name.", xbmc.LOGERROR)
            return ''
    
    
    # Based on a smart playlist, create a normal playlist that can actually be used by us
    def makeChannelList(self, channel, chtype, setting1, setting2, setting3, setting4, append = False):
        self.log('makeChannelList, CHANNEL: ' + str(channel))
        setProperty("PTVL.BackgroundLoading_Finished","false")
        fileListCHK = False
        israndom = False  
        reverseOrder = False
        fileList = []
        setting4 = setting4.replace('Default','0').replace('Random','1').replace('Reverse','2') 

        # Set Media Sort
        if chtype in [7, 10, 11, 12, 13]:
            if setting4 == '0':
                #DEFAULT
                israndom = False  
                reverseOrder = False
            elif setting4 == '1':
                #RANDOM
                israndom = True
                reverseOrder = False
            elif setting4 == '2':
                #REVERSE ORDER
                israndom = False
                reverseOrder = True
        
        #Set Limit Local or Global
        if (chtype == 7 or chtype > 9) and setting3 != '' and len(setting3) > 0:
            try:
                limit = int(setting3)
            except:
                limit = self.limit
            self.log("makeChannelList, Overriding Global Parse-limit to " + str(limit))
        else:
            if chtype == 10 and self.limit == 0 or self.limit > 200:
                limit = 200
            elif chtype in [8,9]:
                limit = 72
            elif chtype >= 7 and self.limit == 0:
                limit = 1000
            else:
                limit = self.limit
            self.log("makeChannelList, Using Global Parse-limit " + str(limit))
            
        # Directory
        if chtype == 7:
            fileList = self.createDirectoryPlaylist(setting1, setting3, setting4, limit)     
            
        # LiveTV
        elif chtype == 8:
            self.log("Building LiveTV Channel, " + setting1 + " , " + setting2 + " , " + setting3)
            
            # HDHomeRun #
            if setting2[0:9] == 'hdhomerun' and REAL_SETTINGS.getSetting('HdhomerunMaster') == "true":
                #If you're using a HDHomeRun Dual and want Tuner 1 assign false. *Thanks Blazin912*
                self.log("Building LiveTV using tuner0")
                setting2 = re.sub(r'\d/tuner\d',"0/tuner0",setting2)
            elif setting2[0:9] == 'hdhomerun' and REAL_SETTINGS.getSetting('HdhomerunMaster') == "false":
                self.log("Building LiveTV using tuner1")
                setting2 = re.sub(r'\d/tuner\d',"1/tuner1",setting2) 
            
            # Validate Feed #
            fileListCHK = self.Valid_ok(setting2)
            if fileListCHK == True:
                fileList = self.buildLiveTVFileList(setting1, setting2, setting3, setting4, limit)
            else:
                self.log('makeChannelList, CHANNEL: ' + str(channel) + ', CHTYPE: ' + str(chtype), 'fileListCHK invalid: ' + str(setting2))
                return
                
        # InternetTV  
        elif chtype == 9:
            self.log("Building InternetTV Channel, " + setting1 + " , " + setting2 + " , " + setting3)
            # Validate Feed #
            fileListCHK = self.Valid_ok(setting2)
            if fileListCHK == True:
                fileList = self.buildInternetTVFileList(setting1, setting2, setting3, setting4, limit)
            else:
                self.log('makeChannelList, CHANNEL: ' + str(channel) + ', CHTYPE: ' + str(chtype), 'fileListCHK invalid: ' + str(setting2))
                return 
                
        # Youtube                          
        elif chtype == 10:
            if self.youtube_ok != False:
                setting2 = setting2.replace('Multi Playlist','7').replace('Multi Channel','8').replace('Raw gdata','9')
                setting2 = setting2.replace('User Favorites','1').replace('Search Query','5').replace('User Subscription','1')
                setting2 = setting2.replace('Seasonal','31').replace('Channel','1').replace('Playlist','2')
                self.log("Building Youtube Channel " + setting1 + " using type " + setting2 + "...")
                
                if setting2 == '31':
                    today = datetime.datetime.now()
                    month = today.strftime('%B')
                    #If Month != Update
                    if setting1.lower() != month.lower():
                        ADDON_SETTINGS.setSetting("Channel_" + str(channel) + "_1", month)   
                        setting1 = month
                        
                self.YT_VideoCount = 0
                fileList = self.createYoutubeFilelist(setting1, setting2, setting3, setting4, limit)
            else:
                self.log('makeChannelList, CHANNEL: ' + str(channel) + ', CHTYPE: ' + str(chtype), 'self.youtube_ok invalid: ' + str(setting2))
                return   
                
        # RSS/iTunes/feedburner/Podcast   
        elif chtype == 11:# Validate Feed #
            fileListCHK = self.Valid_ok(setting1)
            if fileListCHK == True:
                self.log("Building RSS Feed " + setting1 + " using type " + setting2 + "...")
                fileList = self.createRSSFileList(setting1, setting2, setting3, setting4, limit)      
            else:
                self.log('makeChannelList, CHANNEL: ' + str(channel) + ', CHTYPE: ' + str(chtype), 'fileListCHK invalid: ' + str(setting2))
                return   
                
        # MusicVideos
        elif chtype == 13:
            self.log("Building Music Videos")
            fileList = self.MusicVideos(setting1, setting2, setting3, setting4, limit)    
            
        # Extras
        elif chtype == 14 and isDon() == True:
            self.log("Extras, " + setting1 + "...")
            fileList = self.extras(setting1, setting2, setting3, setting4, channel)     
            
        # Direct Plugin
        elif chtype == 15:
            # Validate Feed #
            fileListCHK = self.plugin_ok(setting1)
            if fileListCHK == True:
                self.log("Building Plugin Channel, " + setting1 + "...")
                fileList = self.BuildPluginFileList(setting1, setting2, setting3, setting4, limit)            
            else:
                self.log('makeChannelList, CHANNEL: ' + str(channel) + ', CHTYPE: ' + str(chtype), 'fileListCHK invalid: ' + str(setting2))
                return 
                
        # Direct UPNP
        elif chtype == 16:
            self.log("Building UPNP Channel, " + setting1 + "...")
            fileList = self.BuildUPNPFileList(setting1, setting2, setting3, setting4, limit)  
                
        # LocalTV
        else:
            if chtype == 0:
                if FileAccess.copy(setting1, MADE_CHAN_LOC + os.path.split(setting1)[1]) == False:
                    if FileAccess.exists(MADE_CHAN_LOC + os.path.split(setting1)[1]) == False:
                        self.log("Unable to copy or find playlist " + setting1)
                        return False

                fle = MADE_CHAN_LOC + os.path.split(setting1)[1]
            else:
                fle = self.makeTypePlaylist(chtype, setting1, setting2)
           
            if len(fle) == 0:
                self.log('Unable to locate the playlist for channel ' + str(channel), xbmc.LOGERROR)
                return False

            try:
                xml = FileAccess.open(fle, "r")
            except Exception,e:
                self.log("makeChannelList Unable to open the smart playlist " + fle, xbmc.LOGERROR)
                return False

            try:
                dom = parse(xml)
            except Exception,e:
                self.log('makeChannelList Problem parsing playlist ' + fle, xbmc.LOGERROR)
                xml.close()
                return False

            xml.close()

            if self.getSmartPlaylistType(dom) == 'mixed':
                if self.incBCTs == True:
                    self.log("makeChannelList, adding CTs to mixed...")
                    PrefileList = self.buildMixedFileList(dom, channel, limit)
                    fileList = self.insertBCTfiles(channel, PrefileList, 'mixed')
                else:
                    fileList = self.buildMixedFileList(dom, channel, limit)

            elif self.getSmartPlaylistType(dom) == 'movies':
                if REAL_SETTINGS.getSetting('Movietrailers') != 'true':
                    self.incBCTs == False
                    
                if self.incBCTs == True:
                    self.log("makeChannelList, adding Trailers to movies...")
                    PrefileList = self.buildFileList(fle, channel, limit)
                    fileList = self.insertBCTfiles(channel, PrefileList, 'movies')
                else:
                    fileList = self.buildFileList(fle, channel, limit)
            
            elif self.getSmartPlaylistType(dom) == 'episodes':
                if self.incBCTs == True:
                    self.log("makeChannelList, adding BCT's to episodes...")
                    PrefileList = self.buildFileList(fle, channel, limit)
                    fileList = self.insertBCTfiles(channel, PrefileList, 'episodes')
                else:
                    fileList = self.buildFileList(fle, channel, limit)
            else:
                fileList = self.buildFileList(fle, channel, limit)

            try:
                order = dom.getElementsByTagName('order')

                if order[0].childNodes[0].nodeValue.lower() == 'random':
                    israndom = True
            except Exception,e:
                pass

        try:
            if append == True:
                channelplaylist = FileAccess.open(CHANNELS_LOC + "channel_" + str(channel) + ".m3u", "r+")
                channelplaylist.seek(0, 2)
            else:
                channelplaylist = FileAccess.open(CHANNELS_LOC + "channel_" + str(channel) + ".m3u", "w")
        except Exception,e:
            self.log('Unable to open the cache file ' + CHANNELS_LOC + 'channel_' + str(channel) + '.m3u', xbmc.LOGERROR)
            return False

        if append == False:
            channelplaylist.write(uni("#EXTM3U\n"))
            #first queue m3u
            
        if fileList != None:  
            if len(fileList) == 0:
                self.log("Unable to get information about channel " + str(channel), xbmc.LOGERROR)
                channelplaylist.close()
                return False

        if israndom:
            random.shuffle(fileList)
            
        if reverseOrder:
            fileList.reverse()

        # if len(fileList) > 16384:
            # fileList = fileList[:16384]
            
        if len(fileList) > 4096:
            fileList = fileList[:4096]     
            
        fileList = self.runActions(RULES_ACTION_LIST, channel, fileList)
        self.channels[channel - 1].isRandom = israndom

        # if append:
            # if len(fileList) + self.channels[channel - 1].Playlist.size() > 16384:
                # fileList = fileList[:(16384 - self.channels[channel - 1].Playlist.size())]
        # else:
            # if len(fileList) > 16384:
                # fileList = fileList[:16384]

        if append:
            if len(fileList) + self.channels[channel - 1].Playlist.size() > 4096:
                fileList = fileList[:(4096 - self.channels[channel - 1].Playlist.size())]
        else:
            if len(fileList) > 4096:
                fileList = fileList[:4096]

        # Write each entry into the new playlist
        for string in fileList:
            channelplaylist.write(uni("#EXTINF:") + uni(string) + uni("\n"))
            
        channelplaylist.close()
        self.log('makeChannelList return')
        return True

        
    def makeTypePlaylist(self, chtype, setting1, setting2):
    
        if chtype == 1:
            if len(self.networkList) == 0:
                self.fillTVInfo()
            return self.createNetworkPlaylist(setting1)
            
        elif chtype == 2:
            if len(self.studioList) == 0:
                self.fillMovieInfo()
            return self.createStudioPlaylist(setting1)
            
        elif chtype == 3:
            if len(self.showGenreList) == 0:
                self.fillTVInfo()
            return self.createGenrePlaylist('episodes', chtype, setting1)
            
        elif chtype == 4:
            if len(self.movieGenreList) == 0:
                self.fillMovieInfo()
            return self.createGenrePlaylist('movies', chtype, setting1)
            
        elif chtype == 5:
            if len(self.mixedGenreList) == 0:
                if len(self.showGenreList) == 0:
                    self.fillTVInfo()

                if len(self.movieGenreList) == 0:
                    self.fillMovieInfo()

                self.mixedGenreList = self.makeMixedList(self.showGenreList, self.movieGenreList)
                self.mixedGenreList.sort(key=lambda x: x.lower())
            return self.createGenreMixedPlaylist(setting1)
            
        elif chtype == 6:
            if len(self.showList) == 0:
                self.fillTVInfo()
            return self.createShowPlaylist(setting1, setting2)    
            
        elif chtype == 12:
            if len(self.musicGenreList) == 0:
                self.fillMusicInfo()
            return self.createGenrePlaylist('songs', chtype, setting1)

        self.log('makeTypePlaylists invalid channel type: ' + str(chtype))
        return ''    
    
    
    def createNetworkPlaylist(self, network):
        flename = xbmc.makeLegalFilename(GEN_CHAN_LOC + 'network_' + network + '.xsp')
        
        try:
            fle = FileAccess.open(flename, "w")
        except:
            self.Error('Unable to open the cache file ' + flename, xbmc.LOGERROR)
            return ''

        self.writeXSPHeader(fle, "episodes", self.getChannelName(1, network))
        network = network.lower()
        added = False

        fle.write('    <rule field="tvshow" operator="is">\n')
        
        for i in range(len(self.showList)):
            if self.threadPause() == False:
                fle.close()
                return ''

            if self.showList[i][1].lower() == network:
                theshow = self.cleanString(self.showList[i][0])                
                fle.write('        <value>' + theshow + '</value>\n')            
                added = True
        
        fle.write('    </rule>\n')
        
        self.writeXSPFooter(fle, self.limit, "random")
        fle.close()

        if added == False:
            return ''
        return flename


    def createShowPlaylist(self, show, setting2):
        order = 'random'

        try:
            setting = int(setting2)
            if setting & MODE_ORDERAIRDATE > 0:
                order = 'episode'
        except Exception,e:
            pass

        flename = xbmc.makeLegalFilename(GEN_CHAN_LOC + 'Show_' + show + '_' + order + '.xsp')
        
        try:
            fle = FileAccess.open(flename, "w")
        except Exception,e:
            self.Error('Unable to open the cache file ' + flename, xbmc.LOGERROR)
            return ''

        self.writeXSPHeader(fle, 'episodes', self.getChannelName(6, show))
        show = self.cleanString(show)
        fle.write('    <rule field="tvshow" operator="is">\n')
        fle.write('        <value>' + show + '</value>\n')
        fle.write('    </rule>\n')
        
        self.writeXSPFooter(fle, self.limit, order)
        fle.close()
        return flename

    
    def fillMixedGenreInfo(self):
        if len(self.mixedGenreList) == 0:
            if len(self.showGenreList) == 0:
                self.fillTVInfo()
            if len(self.movieGenreList) == 0:
                self.fillMovieInfo()

            self.mixedGenreList = self.makeMixedList(self.showGenreList, self.movieGenreList)
            self.mixedGenreList.sort(key=lambda x: x.lower())

    
    def makeMixedList(self, list1, list2):
        self.log("makeMixedList")
        newlist = []

        for item in list1:
            curitem = item.lower()

            for a in list2:
                if curitem == a.lower():
                    newlist.append(item)
                    break
        return newlist
    
    
    def createGenreMixedPlaylist(self, genre):
        flename = xbmc.makeLegalFilename(GEN_CHAN_LOC + 'mixed_' + genre + '.xsp')
        
        try:
            fle = FileAccess.open(flename, "w")
        except Exception,e:
            self.Error('Unable to open the cache file ' + flename, xbmc.LOGERROR)
            return ''

        epname = os.path.basename(self.createGenrePlaylist('episodes', 3, genre))
        moname = os.path.basename(self.createGenrePlaylist('movies', 4, genre))
        self.writeXSPHeader(fle, 'mixed', self.getChannelName(5, genre))
        fle.write('    <rule field="playlist" operator="is">' + epname + '</rule>\n')
        fle.write('    <rule field="playlist" operator="is">' + moname + '</rule>\n')
        self.writeXSPFooter(fle, self.limit, "random")
        fle.close()
        return flename


    def createGenrePlaylist(self, pltype, chtype, genre):
        flename = xbmc.makeLegalFilename(GEN_CHAN_LOC + pltype + '_' + genre + '.xsp')
        try:
            fle = FileAccess.open(flename, "w")
        except Exception,e:
            self.Error('Unable to open the cache file ' + flename, xbmc.LOGERROR)
            return ''

        self.writeXSPHeader(fle, pltype, self.getChannelName(chtype, genre))
        genre = self.cleanString(genre)
        fle.write('    <rule field="genre" operator="is">\n')
        fle.write('        <value>' + genre + '</value>\n')
        fle.write('    </rule>\n')
        
        self.writeXSPFooter(fle, self.limit, "random")
        fle.close()
        return flename


    def createStudioPlaylist(self, studio):
        flename = xbmc.makeLegalFilename(GEN_CHAN_LOC + 'Studio_' + studio + '.xsp')
        try:
            fle = FileAccess.open(flename, "w")
        except Exception,e:
            self.Error('Unable to open the cache file ' + flename, xbmc.LOGERROR)
            return ''

        self.writeXSPHeader(fle, "movies", self.getChannelName(2, studio))
        studio = self.cleanString(studio)
        fle.write('    <rule field="studio" operator="is">\n')
        fle.write('        <value>' + studio + '</value>\n')
        fle.write('    </rule>\n')
        
        self.writeXSPFooter(fle, self.limit, "random")
        fle.close()
        return flename
        
        
    def createCinemaExperiencePlaylist(self):
        flename = xbmc.makeLegalFilename(GEN_CHAN_LOC + 'movies_CinemaExperience.xsp')
        twoyearsold = date.today().year - 2
        limit = 25
            
        try:
            fle = FileAccess.open(flename, "w")
        except Exception,e:
            self.Error('Unable to open the cache file ' + flename, xbmc.LOGERROR)
            return ''

        fle.write('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n')
        fle.write('<smartplaylist type="movies">\n')
        fle.write('    <name>Cinema Experience</name>\n')
        fle.write('    <match>all</match>\n')
        fle.write('    <rule field="videoresolution" operator="greaterthan">\n')
        fle.write('        <value>720</value>\n')
        fle.write('    </rule>\n')
        fle.write('    <rule field="playcount" operator="is">\n')
        fle.write('        <value>0</value>\n')
        fle.write('    </rule>\n')
        fle.write('    <rule field="year" operator="greaterthan">\n')
        fle.write('        <value>' + str(twoyearsold) + '</value>\n')
        fle.write('    </rule>\n')
        fle.write('    <group>none</group>\n')
        fle.write('    <limit>'+str(limit)+'</limit>\n')
        fle.write('    <order direction="ascending">random</order>\n')
        fle.write('</smartplaylist>\n')
        fle.close()
        return flename
        
        
    def createRecentlyAddedTV(self):
        flename = xbmc.makeLegalFilename(GEN_CHAN_LOC + 'episodes_RecentlyAddedTV.xsp')
        limit = MEDIA_LIMIT[int(REAL_SETTINGS.getSetting('MEDIA_LIMIT'))]
        try:
            fle = FileAccess.open(flename, "w")
        except Exception,e:
            self.Error('Unable to open the cache file ' + flename, xbmc.LOGERROR)
            return ''

        fle.write('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n')
        fle.write('<smartplaylist type="episodes">\n')
        fle.write('    <name>Recently Added TV</name>\n')
        fle.write('    <match>all</match>\n')
        fle.write('    <rule field="dateadded" operator="inthelast">\n')
        fle.write('        <value>14</value>\n')
        fle.write('    </rule>\n')
        fle.write('    <limit>'+str(limit)+'</limit>\n')
        fle.write('    <order direction="descending">dateadded</order>\n')
        fle.write('</smartplaylist>\n')
        fle.close()
        return flename
        
    
    def createRecentlyAddedMovies(self):
        flename = xbmc.makeLegalFilename(GEN_CHAN_LOC + 'movies_RecentlyAddedMovies.xsp')
        limit = MEDIA_LIMIT[int(REAL_SETTINGS.getSetting('MEDIA_LIMIT'))]
        try:
            fle = FileAccess.open(flename, "w")
        except Exception,e:
            self.Error('Unable to open the cache file ' + flename, xbmc.LOGERROR)
            return ''

        fle.write('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n')
        fle.write('<smartplaylist type="movies">\n')
        fle.write('    <name>Recently Added Movies</name>\n')
        fle.write('    <match>all</match>\n')
        fle.write('    <rule field="dateadded" operator="inthelast">\n')
        fle.write('        <value>14</value>\n')
        fle.write('    </rule>\n')
        fle.write('    <limit>'+str(limit)+'</limit>\n')
        fle.write('    <order direction="descending">dateadded</order>\n')
        fle.write('</smartplaylist>\n')
        fle.close()
        return flename
        

    def createDirectoryPlaylist(self, setting1, setting3, setting4, limit):
        self.log("createDirectoryPlaylist")
        fileList = []
        LocalLST = []
        LocalFLE = ''
        filecount = 0 
        LiveID = 'other|0|0|False|1|NR|'
        
        if not setting1.endswith('/'):
            setting1 = os.path.join(setting1,'')
            
        LocalLST = self.walk(setting1)

        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Videos")
        
        for i in range(len(LocalLST)):         
            if self.threadPause() == False:
                del fileList[:]
                break
                
            LocalFLE = (LocalLST[i])[0]
            duration = self.videoParser.getVideoLength(LocalFLE)
                                            
            if duration == 0 and LocalFLE[-4:].lower() == 'strm':
                duration = 3600
                self.log("createDirectoryPlaylist, no strm duration found defaulting to 3600")
                    
            if duration > 0:
                filecount += 1
                
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding %s Videos" % str(filecount))
                    
                title = (os.path.split(LocalFLE)[1])
                title = os.path.splitext(title)[0].replace('.', ' ')
                description = LocalFLE.replace('//','/').replace('/','\\')
                
                tmpstr = str(duration) + ',' + title + "//" + 'Directory Video' + "//" + description + "//" + 'Unknown' + "////" + LiveID + '\n' + (LocalFLE)
                tmpstr = tmpstr[:2036]
                fileList.append(tmpstr)
                    
                if filecount >= limit:
                    break
                    
        if filecount == 0:
            self.log('Unable to access Videos files in ' + setting1)
        return fileList


    def writeXSPHeader(self, fle, pltype, plname):
        fle.write('<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>\n')
        fle.write('<smartplaylist type="'+pltype+'">\n')
        plname = self.cleanString(plname)
        fle.write('    <name>'+plname+'</name>\n')
        fle.write('    <match>one</match>\n')


    def writeXSPFooter(self, fle, limit, order):
        if limit > 0:
            fle.write('    <limit>'+str(limit)+'</limit>\n')
        fle.write('    <order direction="ascending">' + order + '</order>\n')
        fle.write('</smartplaylist>\n')
    
    
    def CleanPlayableFile(self, file):
        self.log('CleanPlayableFile')
        file = file.replace('plugin://plugin.video.youtube/?action=play_video&videoid=', self.youtube_ok)
        file = file.replace('plugin://plugin.video.bromix.youtube/play/?video_id=', self.youtube_ok)
        return file
        

    def CleanLabels(self, text, format='title'):
        self.logDebug('CleanLabels, in = ' + text)
        text = re.sub('\[COLOR (.+?)\]', '', text)
        text = re.sub('\[/COLOR\]', '', text)
        text = re.sub('\[COLOR=(.+?)\]', '', text)
        text = re.sub('\[color (.+?)\]', '', text)
        text = re.sub('\[/color\]', '', text)
        text = re.sub('\[Color=(.+?)\]', '', text)
        text = re.sub('\[/Color\]', '', text)
        text = text.replace("[UPPERCASE]",'')
        text = text.replace("[/UPPERCASE]",'')
        text = text.replace("[CR]",'')
        text = text.replace("()",'')
        text = text.replace("\ ",'')
        text = text.replace("\\",'')
        text = text.replace("/ ",'')
        text = text.replace("//",'')
        text = text.replace("[B]",'')
        text = text.replace("[/B]",'')
        text = text.replace("[I]",'')
        text = text.replace("[/I]",'')
        text = text.replace("[HD]",'')
        text = text.replace("[CC]",'')
        text = text.replace("[Cc]",'')
        text = text.replace("(SUB)",'')
        text = text.replace("(DUB)",'')
        text = text.replace("\n", "")
        text = text.replace("\r", "")
        text = text.replace("\t", "")
        text = text.replace("*", "")
        text = text.replace(" [Favorite]", "")
        text = text.replace(" [DRM]", "")
        text = text.strip()
        if format == 'title':
            text = (text.title()).replace("'S","'s")
        elif format == 'upper':
            text = (text.upper())
        elif format == 'lower':
            text = (text.lower())
        self.logDebug('CleanLabels, out = ' + text)
        return text
    
    
    def cleanRating(self, rating):
        self.log("cleanRating")
        rating = rating.replace('Rated ','').replace('US:','').replace('UK:','').replace('Unrated','NR').replace('NotRated','NR').replace('N/A','NR').replace('NA','NR').replace('APPROVED','NR').replace('Approved','NR').replace('not rated','NR').replace('UNRAT','NR')
        return rating
        # rating = rating.replace('Unrated','NR').replace('NotRated','NR').replace('N/A','NR').replace('Approved','NR')
    

    def cleanString(self, string):
        newstr = uni(string)
        newstr = newstr.replace('&', '&amp;')
        newstr = newstr.replace('>', '&gt;')
        newstr = newstr.replace('<', '&lt;')
        return uni(newstr)

    
    def uncleanString(self, string):
        self.log("uncleanString")
        newstr = string
        newstr = newstr.replace('&amp;', '&')
        newstr = newstr.replace('&gt;', '>')
        newstr = newstr.replace('&lt;', '<')
        return uni(newstr)
               
            
    def fillMusicInfo(self, sortbycount = False):
        self.log("fillMusicInfo")
        self.musicGenreList = []
        json_query = ('{"jsonrpc": "2.0", "method": "AudioLibrary.GetAlbums", "params": {"properties":["genre"]}, "id": 1}')
        
        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Music")

        json_folder_detail = self.sendJSON(json_query)
        detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_folder_detail)

        for f in detail:
            if self.threadPause() == False:
                del self.musicGenreList[:]
                return

            match = re.search('"genre" *: *\[(.*?)\]', f)
          
            if match:
                genres = match.group(1).split(',')
               
                for genre in genres:
                    found = False
                    curgenre = genre.lower().strip('"').strip()

                    for g in range(len(self.musicGenreList)):
                        if self.threadPause() == False:
                            del self.musicGenreList[:]
                            return
                            
                        itm = self.musicGenreList[g]

                        if sortbycount:
                            itm = itm[0]

                        if curgenre == itm.lower():
                            found = True

                            if sortbycount:
                                self.musicGenreList[g][1] += 1

                            break

                    if found == False:
                        if sortbycount:
                            self.musicGenreList.append([genre.strip('"').strip(), 1])
                        else:
                            self.musicGenreList.append(genre.strip('"').strip())
    
        if sortbycount:
            self.musicGenreList.sort(key=lambda x: x[1], reverse = True)
        else:
            self.musicGenreList.sort(key=lambda x: x.lower())

        if (len(self.musicGenreList) == 0):
            self.logDebug(json_folder_detail)

        self.log("found genres " + str(self.musicGenreList))
     
    
    def fillTVInfo(self, sortbycount = False):
        self.log("fillTVInfo")
        json_query = ('{"jsonrpc": "2.0", "method": "VideoLibrary.GetTVShows", "params": {"properties":["studio", "genre"]}, "id": 1}')

        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Videos")

        json_folder_detail = self.sendJSON(json_query)
        detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_folder_detail)

        for f in detail:
            if self.threadPause() == False:
                del self.networkList[:]
                del self.showList[:]
                del self.showGenreList[:]
                return

            match = re.search('"studio" *: *\[(.*?)\]', f)
            network = ''

            if match:
                network = (match.group(1).split(','))[0]
                network = network.strip('"').strip()
                found = False

                for item in range(len(self.networkList)):
                    if self.threadPause() == False:
                        del self.networkList[:]
                        del self.showList[:]
                        del self.showGenreList[:]
                        return

                    itm = self.networkList[item]

                    if sortbycount:
                        itm = itm[0]

                    if itm.lower() == network.lower():
                        found = True

                        if sortbycount:
                            self.networkList[item][1] += 1

                        break

                if found == False and len(network) > 0:
                    if sortbycount:
                        self.networkList.append([network, 1])
                    else:
                        self.networkList.append(network)

            match = re.search('"label" *: *"(.*?)",', f)

            if match:
                show = match.group(1).strip()
                self.showList.append([show, network])
                
            match = re.search('"genre" *: *\[(.*?)\]', f)

            if match:
                genres = match.group(1).split(',')
                
                for genre in genres:
                    found = False
                    curgenre = genre.lower().strip('"').strip()

                    for g in range(len(self.showGenreList)):
                        if self.threadPause() == False:
                            del self.networkList[:]
                            del self.showList[:]
                            del self.showGenreList[:]
                            return

                        itm = self.showGenreList[g]

                        if sortbycount:
                            itm = itm[0]

                        if curgenre == itm.lower():
                            found = True

                            if sortbycount:
                                self.showGenreList[g][1] += 1

                            break

                    if found == False:
                        if sortbycount:
                            self.showGenreList.append([genre.strip('"').strip(), 1])
                        else:
                            self.showGenreList.append(genre.strip('"').strip())

        if sortbycount:
            self.networkList.sort(key=lambda x: x[1], reverse = True)
            self.showGenreList.sort(key=lambda x: x[1], reverse = True)
        else:
            self.networkList.sort(key=lambda x: x.lower())
            self.showGenreList.sort(key=lambda x: x.lower())

        if (len(self.showList) == 0) and (len(self.showGenreList) == 0) and (len(self.networkList) == 0):
            self.logDebug(json_folder_detail)
            
        self.showList = removeStringElem(self.showList)
        self.showGenreList = removeStringElem(self.showGenreList)
        self.networkList = removeStringElem(self.networkList)
        
        self.log("found shows " + str(self.showList))
        self.log("found genres " + str(self.showGenreList))
        self.log("fillTVInfo return " + str(self.networkList))


    def fillMovieInfo(self, sortbycount = False):
        self.log("fillMovieInfo")
        studioList = []
        json_query = ('{"jsonrpc": "2.0", "method": "VideoLibrary.GetMovies", "params": {"properties":["studio", "genre"]}, "id": 1}')

        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Videos")

        json_folder_detail = self.sendJSON(json_query)
        detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_folder_detail)

        for f in detail:
            if self.threadPause() == False:
                del self.movieGenreList[:]
                del self.studioList[:]
                del studioList[:]
                break

            match = re.search('"genre" *: *\[(.*?)\]', f)

            if match:
                genres = match.group(1).split(',')

                for genre in genres:
                    found = False
                    curgenre = genre.lower().strip('"').strip()

                    for g in range(len(self.movieGenreList)):
                        itm = self.movieGenreList[g]

                        if sortbycount:
                            itm = itm[0]

                        if curgenre == itm.lower():
                            found = True

                            if sortbycount:
                                self.movieGenreList[g][1] += 1

                            break

                    if found == False:
                        if sortbycount:
                            self.movieGenreList.append([genre.strip('"').strip(), 1])
                        else:
                            self.movieGenreList.append(genre.strip('"').strip())

            match = re.search('"studio" *: *\[(.*?)\]', f)
           
            if match:
                studios = match.group(1).split(',')
                
                for studio in studios:
                    curstudio = studio.strip('"').strip()
                    found = False

                    for i in range(len(studioList)):
                        if studioList[i][0].lower() == curstudio.lower():
                            studioList[i][1] += 1
                            found = True
                            break

                    if found == False and len(curstudio) > 0:
                        studioList.append([curstudio, 1])

        maxcount = 0

        for i in range(len(studioList)):
            if studioList[i][1] > maxcount:
                maxcount = studioList[i][1]

        bestmatch = 1
        lastmatch = 1000
        counteditems = 0

        for i in range(maxcount, 0, -1):
            itemcount = 0

            for j in range(len(studioList)):
                if studioList[j][1] == i:
                    itemcount += 1

            if abs(itemcount + counteditems - 8) < abs(lastmatch - 8):
                bestmatch = i
                lastmatch = itemcount

            counteditems += itemcount

        if sortbycount:
            studioList.sort(key=lambda x: x[1], reverse=True)
            self.movieGenreList.sort(key=lambda x: x[1], reverse=True)
        else:
            studioList.sort(key=lambda x: x[0].lower())
            self.movieGenreList.sort(key=lambda x: x.lower())

        for i in range(len(studioList)):
            if studioList[i][1] >= bestmatch:
                if sortbycount:
                    self.studioList.append([studioList[i][0], studioList[i][1]])
                else:
                    self.studioList.append(studioList[i][0])

        if (len(self.movieGenreList) == 0) and (len(self.studioList) == 0):
            self.logDebug(json_folder_detail)

        self.movieGenreList = removeStringElem(self.movieGenreList)
        self.studioList = removeStringElem(self.studioList)
        
        self.log("found genres " + str(self.movieGenreList))
        self.log("fillMovieInfo return " + str(self.studioList))


    def makeMixedList(self, list1, list2):
        self.log("makeMixedList")
        newlist = []

        for item in list1:
            curitem = item.lower()

            for a in list2:
                if curitem == a.lower():
                    newlist.append(item)
                    break

        self.log("makeMixedList return " + str(newlist))
        return newlist
        
        
    # pack to string for playlist
    def packGenreLiveID(self, GenreLiveID):
        self.log("packGenreLiveID, GenreLiveID = " + str(GenreLiveID))
        genre = GenreLiveID[0]
        LiveID = '|'.join(str(x) for x in GenreLiveID[1:]) + '|'
        return genre, LiveID
        
        
    # unpack to list for parsing
    def unpackLiveID(self, LiveID):
        self.log("unpackLiveID, LiveID = " + LiveID)
        LiveID = LiveID.split('|')
        return LiveID


    def isMedia3D(self, path):
        flag3d = False
        FILTER_3D = ['3d','sbs','fsbs','ftab','hsbs','h.sbs','h-sbs','htab','sbs3d','3dbd','halfsbs','half.sbs','half-sbs','fullsbs','full.sbs','full-sbs','3dsbs','3d.sbs']
        for i in range(len(FILTER_3D)):
            if FILTER_3D[i] in path:   
                flag3d = True                        
                break
        return flag3d
        

    def buildFileList(self, dir_name, channel, limit, FleType = 'video'): ##fix music channel todo
        self.log("buildFileList")
        fileList = []
        seasoneplist = []
        file_detail = []
        filecount = 0
        LiveID = 'other|0|0|False|1|NR|'
        json_query = uni('{"jsonrpc": "2.0", "method": "Files.GetDirectory", "params": {"directory": "%s", "media": "%s", "properties":["title","year","mpaa","imdbnumber","description","season","episode","playcount","genre","duration","runtime","showtitle","album","artist","plot","plotoutline","tagline","tvshowid"]}, "id": 1}' % (self.escapeDirJSON(dir_name), FleType))

        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Videos, querying database")
        
        json_folder_detail = self.sendJSON(json_query)
        file_detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_folder_detail)

        for f in file_detail:
            if self.threadPause() == False:
                del fileList[:]
                break
                
            istvshow = False
            flag3d = False
            Managed = False
            match = re.search('"file" *: *"(.*?)",', f)
            
            if match:
                if(match.group(1).endswith("/") or match.group(1).endswith("\\")):
                    fileList.extend(self.buildFileList(match.group(1), channel, limit))
                else:
                    f = self.runActions(RULES_ACTION_JSON, channel, f)
                    duration = re.search('"duration" *: *([0-9]*?),', f)
                    
                    # If music duration returned, else 0
                    try:
                        dur = int(duration.group(1))
                    except Exception,e:
                        dur = 0
                        pass
                        
                    # Accurate duration
                    if dur == 0:
                        try:
                            dur = self.videoParser.getVideoLength(uni(match.group(1)).replace("\\\\", "\\"))
                        except Exception,e:
                            dur = 0
                            pass
                            
                    # Less accurate duration
                    if dur == 0:
                        duration = re.search('"runtime" *: *([0-9]*?),', f)
                        try:
                            dur = int(duration.group(1))
                        except Exception,e:
                            dur = 0
                            pass
                    
                    # Filter 3D Media.
                    if self.inc3D == False:
                        flag3d = self.isMedia3D(match.group(1).replace("\\\\", "\\").lower())

                    # Remove any file types that we don't want (ex. IceLibrary, ie. Strms)
                    if self.incIceLibrary == False:
                        if match.group(1).replace("\\\\", "\\")[-4:].lower() == 'strm':
                            dur = 0
                    else:
                        # Include strms with no duration
                        if dur == 0 and match.group(1).replace("\\\\", "\\")[-4:].lower() == 'strm':
                            dur = 3600    
                    self.logDebug("buildFileList, dur = " + str(dur))  
                    
                    try:
                        if dur > 0:
                            filecount += 1
                            seasonval = -1
                            epval = -1

                            if self.background == False:
                                self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding %s Videos" % str(filecount))
                            
                            tmpstr = str(dur) + ','
                            titles = re.search('"label" *: *"(.*?)",', f)
                            showtitles = re.search('"showtitle" *: *"(.*?)",', f)
                            plots = re.search('"plot" *: *"(.*?)",', f)
                            plotoutlines = re.search('"plotoutline" *: *"(.*?)",', f)
                            years = re.search('"year" *: *([\d.]*\d+)', f)
                            genres = re.search('"genre" *: *\[(.*?)\],', f)
                            playcounts = re.search('"playcount" *: *([\d.]*\d+),', f)
                            imdbnumbers = re.search('"imdbnumber" *: *"(.*?)",', f)
                            ratings = re.search('"mpaa" *: *"(.*?)",', f)
                            descriptions = re.search('"description" *: *"(.*?)",', f)
                            
                            if showtitles != None and len(showtitles.group(1)) > 0:
                                type = 'tvshow'
                                dbids = re.search('"tvshowid" *: *([\d.]*\d+),', f)
                                epids = re.search('"id" *: *([\d.]*\d+),', f)
                            else:
                                type = 'movie'
                                dbids = re.search('"id" *: *([\d.]*\d+),', f)  
                                epids = None

                            # if possible find year by title
                            try:
                                year = int(years.group(1))
                            except:
                                try:
                                    if type == 'tvshow':
                                        year = int(((showtitles.group(1)).split(' ('))[1].replace(')',''))
                                    else:
                                        year = int(((titles.group(1)).split(' ('))[1].replace(')',''))
                                except Exception,e:
                                    year = 0
                                    pass
                                    
                            if genres != None and len(genres.group(1)) > 0:
                                genre = ((genres.group(1).split(',')[0]).replace('"',''))
                            else:
                                genre = 'Unknown'
                                
                            if playcounts != None and len(playcounts.group(1)) > 0:
                                playcount = int(playcounts.group(1))
                            else:
                                playcount = 1
                    
                            self.logDebug("buildFileList, playcount = " + str(playcount))  
                            
                            if ratings != None and len(ratings.group(1)) > 0:
                                rating = self.cleanRating(ratings.group(1))
                                if type == 'movie':
                                    rating = rating[0:5]
                                    try:
                                        rating = rating.split(' ')[0]
                                    except:
                                        pass
                            else:
                                rating = 'NR'

                            if imdbnumbers != None and len(imdbnumbers.group(1)) > 0:
                                imdbnumber = imdbnumbers.group(1)
                            else:
                                imdbnumber = 0

                            
                            if epids != None and len(epids.group(1)) > 0:
                                epid = int((epids.group(1)).split(',')[0])
                            else:
                                epid = 0
                                
                            self.logDebug("buildFileList, epid = " + str(epid))
                            
                            if dbids != None and len(dbids.group(1)) > 0:
                                dbid = int((dbids.group(1)).split(',')[0])
                            else:
                                dbid = 0
                                
                            self.logDebug("buildFileList, dbid = " + str(dbid))
                            
                            if plots and len(plots.group(1)) > 0:
                                theplot = (plots.group(1)).replace('\\','').replace('\n','')
                            elif descriptions and len(descriptions.group(1)) > 0:
                                theplot = (descriptions.group(1)).replace('\\','').replace('\n','')
                            elif plotoutlines and len(plotoutlines.group(1)) > 0:
                                theplot = (plotoutlines.group(1)).replace('\\','').replace('\n','')
                            else:
                                theplot = (titles.group(1)).replace('\\','').replace('\n','')
                            
                            try:
                                theplot = (self.trim(theplot, 350, '...'))
                            except Exception,e:
                                theplot = (theplot[:350])

                            # This is a TV show
                            if showtitles != None and len(showtitles.group(1)) > 0:
                                season = re.search('"season" *: *([0-9]*?),', f)
                                episode = re.search('"episode" *: *([0-9]*?),', f)
                                swtitle = (titles.group(1)).replace('\\','')
                                swtitle = (swtitle.split('.', 1)[-1]).replace('. ','')
                                dbid = str(dbid) +':'+ str(epid)
                                
                                try:
                                    seasonval = int(season.group(1))
                                    epval = int(episode.group(1))
                                    swtitle = (('0' if seasonval < 10 else '') + str(seasonval) + 'x' + ('0' if epval < 10 else '') + str(epval) + ' - ' + (swtitle)).replace('  ',' ')
                                except Exception,e:
                                    self.log("Season/Episode formatting failed" + str(e))
                                    seasonval = -1
                                    epval = -1

                                if REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true':  
                                    year, imdbnumber, genre, rating, Managed, tagline = self.getEnhancedGuideData(showtitles.group(1), year, imdbnumber, genre, rating, type)
                                    
                                GenreLiveID = [genre, type, imdbnumber, dbid, Managed, playcount, rating] 
                                genre, LiveID = self.packGenreLiveID(GenreLiveID)
                                tmpstr += (showtitles.group(1)) + "//" + swtitle + "//" + theplot + "//" + genre + "////" + LiveID
                                istvshow = True
                            else:                  
                                album = re.search('"album" *: *"(.*?)"', f)
                                # This is a movie
                                if not album or len(album.group(1)) == 0:
                                
                                    label = titles.group(1)  
                                    showtitle = label  
                                    dbid = str(dbid)
                                    
                                    if '(' in showtitle and year == 0:
                                        try:
                                            year = int(((showtitle.split('('))[1]).replace(')',''))
                                        except:
                                            pass
                                            
                                    taglines = re.search('"tagline" *: *"(.*?)"', f)
                                    if taglines and len(taglines.group(1)) > 0:
                                        tagline = (taglines.group(1)).replace('\\','')
                                    else:
                                        tagline = ''
                                    
                                    if REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true':   
                                        try:
                                            label = showtitle.split(' (')[0]
                                        except:
                                            pass
                                            
                                        year, imdbnumber, genre, rating, Managed, tagline = self.getEnhancedGuideData(label, year, imdbnumber, genre, rating, type, tagline)
                                     
                                    if not '(' in label and year != 0:
                                        showtitle = label + ' ('+str(year)+')'
                                        
                                    GenreLiveID = [genre, type, imdbnumber, dbid, Managed, playcount, rating]
                                    genre, LiveID = self.packGenreLiveID(GenreLiveID)           
                                    tmpstr += showtitle + "//" + tagline + "//" + theplot + "//" + (genre) + "////" + (LiveID)
                                
                                else: #Music
                                    LiveID = 'music|0|0|False|1|NR|'
                                    artist = re.search('"artist" *: *"(.*?)"', f)
                                    tmpstr += album.group(1) + "//" + artist.group(1) + "//" + 'Music' + "////" + LiveID
                            
                            file = unquote(match.group(1))
                            tmpstr = tmpstr
                            tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                            tmpstr = tmpstr + '\n' + file.replace("\\\\", "\\")
                            
                            if self.channels[channel - 1].mode & MODE_ORDERAIRDATE > 0:
                                seasoneplist.append([seasonval, epval, tmpstr])                        
                            else:
                                if flag3d == True:
                                    self.movie3Dlist.append(tmpstr)
                                else:
                                    fileList.append(tmpstr)
                    except Exception,e:
                        self.log('buildFileList, failed...' + str(e))
                        pass
            else:
                continue

        if self.channels[channel - 1].mode & MODE_ORDERAIRDATE > 0:
            seasoneplist.sort(key=lambda seep: seep[1])
            seasoneplist.sort(key=lambda seep: seep[0])

            for seepitem in seasoneplist:
                fileList.append(seepitem[2])

        if filecount == 0:
            self.logDebug(json_folder_detail)

        self.log("buildFileList return")
        return fileList


    def buildMixedFileList(self, dom1, channel, limit):
        self.log('buildMixedFileList')
        fileList = []
        try:
            rules = dom1.getElementsByTagName('rule')
            order = dom1.getElementsByTagName('order')
        except Exception,e:
            self.log('buildMixedFileList Problem parsing playlist ' + filename, xbmc.LOGERROR)
            xml.close()
            
            return fileList

        for rule in rules:
            rulename = rule.childNodes[0].nodeValue

            if FileAccess.exists(xbmc.translatePath('special://profile/playlists/video/') + rulename):
                FileAccess.copy(xbmc.translatePath('special://profile/playlists/video/') + rulename, MADE_CHAN_LOC + rulename)
                fileList.extend(self.buildFileList(MADE_CHAN_LOC + rulename, channel, limit))
            else:
                fileList.extend(self.buildFileList(GEN_CHAN_LOC + rulename, channel, limit))

        self.log("buildMixedFileList returning")
        return fileList

        
    # *Thanks sphere, taken from plugin.video.ted.talks
    # People still using Python <2.7 201303 :(
    def __total_seconds__(self, delta):
        try:
            return delta.total_seconds()
        except AttributeError:
            return int((delta.microseconds + (delta.seconds + delta.days * 24 * 3600) * 10 ** 6)) / 10 ** 6

            
    def parsePVRDate(self, dateString):
        if dateString is not None:
            t = time.strptime(dateString, '%Y-%m-%d %H:%M:%S')
            tmpDate = datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
            timestamp = calendar.timegm(tmpDate.timetuple())
            local_dt = datetime.datetime.fromtimestamp(timestamp)
            assert tmpDate.resolution >= timedelta(microseconds=1)
            return local_dt.replace(microsecond=tmpDate.microsecond) 
        else:
            return None
   
   
    def parseUTCXMLTVDate(self, dateString):
        if dateString is not None:
            if dateString.find(' ') != -1:
                # remove timezone information
                dateString = dateString[:dateString.find(' ')]
            t = time.strptime(dateString, '%Y%m%d%H%M%S')
            tmpDate = datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
            timestamp = calendar.timegm(tmpDate.timetuple())
            local_dt = datetime.datetime.fromtimestamp(timestamp)
            assert tmpDate.resolution >= timedelta(microseconds=1)
            return local_dt.replace(microsecond=tmpDate.microsecond) 
        else:
            return None
       
       
    def parseXMLTVDate(self, dateString, offset=0):
        if dateString is not None:
            if dateString.find(' ') != -1:
                # remove timezone information
                dateString = dateString[:dateString.find(' ')]
            t = time.strptime(dateString, '%Y%m%d%H%M%S')
            d = datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
            d += datetime.timedelta(hours = offset)
            return d
        else:
            return None
            
            
    def buildLiveTVFileList(self, setting1, setting2, setting3, setting4, limit):
        xbmc.log("buildLiveTVFileList_Cache")
        if Primary_Cache_Enabled == True and REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true':  
            try:
                setProperty("PTVL.CHKCache", "false")
                result = liveTV.cacheFunction(self.buildLiveTVFileList_NEW, setting1, setting2, setting3, setting4, limit)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.buildLiveTVFileList_NEW(setting1, setting2, setting3, setting4, limit)
                pass
        else:
            result = self.buildLiveTVFileList_NEW(setting1, setting2, setting3, setting4, limit)
        if not result:
            chname = (self.getChannelName(9, self.settingChannel))
            result = self.buildInternetTVFileList('5400', setting2, chname, 'Guide-data from ' + str(setting3) + ' is currently available to donors only.', 24)
        return result  
        
    
    def buildLiveTVFileList_NEW(self, setting1, setting2, setting3, setting4, limit):
        self.log("buildLiveTVFileList_NEW")  
        showList = []
        # Validate XMLTV Data #
        xmltvValid = self.xmltv_ok(setting3)
        if xmltvValid == True: 
            now = datetime.datetime.now()
            chname = (self.getChannelName(8, self.settingChannel))
                
            try:
                if setting3 == 'pvr':
                    showList = self.fillLiveTVPVR(setting1, setting2, setting3, setting4, chname, limit)
                    MSG = 'Listing Unavailable, Check your pvr backend'
                else:   
                    showList = self.fillLiveTV(setting1, setting2, setting3, setting4, chname, limit)
                    MSG = 'Listing Unavailable, Check your '+setting3+' xmltv file'
            except Exception,e:
                self.log("buildLiveTVFileList, Error: " + str(e))
                pass              
        return showList     
        
        
    def fillLiveTV(self, setting1, setting2, setting3, setting4, chname, limit):
        self.log("fillLiveTV")
        showList = []
        showcount = 0          
        now = datetime.datetime.now()
                
        try:
            if setting3[0:4] == 'http':
                f = open_url(self.xmlTvFile)
            else:
                f = FileAccess.open(self.xmlTvFile, "r")
                
            if setting3.lower() in UTC_XMLTV:                      
                offset = ((time.timezone / 3600) - 5 ) * -1     
            else:
                offset = 0
                
            if self.background == False:
                self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding LiveTV, parsing " + chname)

            context = ET.iterparse(f, events=("start", "end")) 
            context = iter(context)
            event, root = context.next()

            for event, elem in context:
                if self.threadPause() == False:
                    del showList[:]
                    break
                try:    
                    id = 0
                    imdbid = 0
                    tvdbid = 0
                    seasonNumber = 0
                    episodeNumber = 0
                    Managed = False
                    episodeName = ''
                    episodeDesc = ''
                    episodeGenre = ''
                    tagline = ''
                    dd_progid = ''
                    type = ''
                    genre = 'Unknown'
                    rating = 'NR'
                    LiveID = 'tvshow|0|0|False|1|NR|'
                    thumburl = 0
                    
                    if event == "end":
                        if elem.tag == "programme":
                            channel = elem.get("channel")
                            if setting1 == channel:
                                self.log("fillLiveTV, setting1 = " + setting1 + ', channel id = ' + channel)
                                title = elem.findtext('title')

                                try:
                                    test = title.split(" *")[1]
                                    title = title.split(" *")[0]
                                    playcount = 0
                                except Exception,e:
                                    playcount = 1
                                    pass

                                icon = None
                                description = elem.findtext("desc")
                                iconElement = elem.find("icon")
                                # todo grab artwork, encode, pass as dbid
                                # todo improve v-chip, mpaa ratings
                                
                                if iconElement is not None:
                                    icon = iconElement.get("src")
                                    thumburl = (icon.encode('base64')).replace('\n','').replace('\r','').replace('\t','')
                                    
                                    # if icon[0:4] == 'http' and REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true':
                                        # Download icon to channel logo folder
                                        # GrabLogo(icon, chname)
                                    
                                subtitle = elem.findtext("sub-title")
                                if not description:
                                    if not subtitle:
                                        description = title  
                                    else:
                                        description = subtitle
                                        
                                if not subtitle:                        
                                    subtitle = 'LiveTV'

                                #Parse the category of the program
                                movie = False
                                category = 'Unknown'
                                categories = ''
                                categoryList = elem.findall("category")
                                
                                for cat in categoryList:
                                    categories += ', ' + cat.text
                                    if cat.text == 'Movie':
                                        movie = True
                                        category = cat.text
                                    elif cat.text == 'Sports':
                                        category = cat.text
                                    elif cat.text == 'Children':
                                        category = 'Kids'
                                    elif cat.text == 'Kids':
                                        category = cat.text
                                    elif cat.text == 'News':
                                        category = cat.text
                                    elif cat.text == 'Comedy':
                                        category = cat.text
                                    elif cat.text == 'Drama':
                                        category = cat.text
                                
                                #Trim prepended comma and space (considered storing all categories, but one is ok for now)
                                categories = categories[2:]
                                
                                #If the movie flag was set, it should override the rest (ex: comedy and movie sometimes come together)
                                if movie == True:
                                    category = 'Movie'
                                    type = 'movie'
                                else:
                                    type = 'tvshow'
                                    
                                #TVDB/TMDB Parsing    
                                #filter unwanted ids by title
                                if title == ('Paid Programming') or subtitle == ('Paid Programming') or description == ('Paid Programming'):
                                    ignoreParse = True
                                else:
                                    ignoreParse = False
                                    
                                if setting3.lower() == 'ptvlguide':
                                    stopDate = self.parseUTCXMLTVDate(elem.get('stop'))
                                    startDate = self.parseUTCXMLTVDate(elem.get('start'))
                                else:
                                    stopDate = self.parseXMLTVDate(elem.get('stop'), offset)
                                    startDate = self.parseXMLTVDate(elem.get('start'), offset)
                                
                                #Enable Enhanced Parsing
                                if REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true' and ignoreParse == False: 
                                    if (((now > startDate and now <= stopDate) or (now < startDate))):
                                        if type == 'tvshow':                                      
                                            try:
                                                year = (title.split(' ('))[1].replace(')','')
                                                title = (title.split(' ('))[0]
                                            except:
                                                try:
                                                    year = elem.findtext('date')[0:4]
                                                except:
                                                    year = 0
                                                    
                                            #Decipher the TVDB ID by using the Zap2it ID in dd_progid
                                            episodeNumList = elem.findall("episode-num")
                                            
                                            for epNum in episodeNumList:
                                                if epNum.attrib["system"] == 'dd_progid':
                                                    dd_progid = epNum.text
                                            
                                            #The Zap2it ID is the first part of the string delimited by the dot
                                            #  Ex: <episode-num system="dd_progid">MV00044257.0000</episode-num>
                                            
                                            dd_progid = dd_progid.split('.',1)[0]
                                            tvdbid = self.getTVDBIDbyZap2it(dd_progid)
                                            
                                            year, id, category, rating, Managed, tagline = self.getEnhancedGuideData(title, year, tvdbid, genre, rating, type)                              
          
                                            # #Find Episode info by subtitle (ie Episode Name). 
                                            # if year != 0:
                                                # titleYR = title + ' (' + str(year) + ')'
                                            # else:   
                                                # titleYR = title
                                            # if subtitle != 'LiveTV':
                                                # episodeName, seasonNumber, episodeNumber = self.getTVINFObySubtitle(titleYR, subtitle)                                       
                                            # else:
                                                # #Find Episode info by air date.
                                                # if tvdbid != 0:
                                                    # #Date element holds the original air date of the program
                                                    # airdateStr = elem.findtext('date')
                                                    # if airdateStr != None:
                                                        # self.log('buildLiveTVFileList, tvdbid by airdate')
                                                        # try:
                                                            # #Change date format into the byAirDate lookup format (YYYY-MM-DD)
                                                            # t = time.strptime(airdateStr, '%Y%m%d')
                                                            # airDateTime = datetime.datetime(t.tm_year, t.tm_mon, t.tm_mday, t.tm_hour, t.tm_min, t.tm_sec)
                                                            # airdate = airDateTime.strftime('%Y-%m-%d')
                                                            # #Only way to get a unique lookup is to use TVDB ID and the airdate of the episode
                                                            # episode = ET.fromstring(self.tvdbAPI.getEpisodeByAirdate(tvdbid, airdate))
                                                            # episode = episode.find("Episode")
                                                            # seasonNumber = episode.findtext("SeasonNumber")
                                                            # episodeNumber = episode.findtext("EpisodeNumber")
                                                            # episodeDesc = episode.findtext("Overview")
                                                            # episodeName = episode.findtext("EpisodeName")
                                                            # try:
                                                                # int(seasonNumber)
                                                                # int(episodeNumber)
                                                            # except:
                                                                # seasonNumber = 0
                                                                # episodeNumber = 0
                                                                # pass
                                                        # except Exception,e:
                                                            # pass

                                            # # Find Episode info by SeasonNum x EpisodeNum
                                            # if (seasonNumber != 0 and episodeNumber != 0):
                                                # episodeName, episodeDesc, episodeGenre = self.getTVINFObySE(titleYR, seasonNumber, episodeNumber)
                                            
                                            # if episodeName:
                                                # subtitle = episodeName

                                            # if episodeDesc:
                                                # description = episodeDesc                                              

                                            # if episodeGenre and category == 'Unknown':
                                                # category = episodeGenre
                                            
                                        else:#Movie
                                            
                                            try:
                                                year = (title.split(' ('))[1].replace(')','')
                                                title = (title.split(' ('))[0]
                                            except:
                                                #Date element holds the original air date of the program
                                                try:
                                                    year = elem.findtext('date')[0:4]
                                                except:
                                                    year = 0
                                                    
                                            if subtitle == 'LiveTV':
                                                tagline = ''
                                                
                                            year, id, category, rating, Managed, subtitle = self.getEnhancedGuideData(title, year, imdbid, genre, rating, type, tagline)
                                            
                                if seasonNumber > 0:
                                    seasonNumber = '%02d' % int(seasonNumber)
                                
                                if episodeNumber > 0:
                                    episodeNumber = '%02d' % int(episodeNumber)
                                         
                                #Read the "new" boolean for this program
                                if elem.find("new") != None:
                                    playcount = 0
                                else:
                                    playcount = 1                        
                                    
                                GenreLiveID = [category,type,id,thumburl,Managed,playcount,rating] 
                                genre, LiveID = self.packGenreLiveID(GenreLiveID) 
                                description = description.replace("\n", "").replace("\r", "")
                                subtitle = subtitle.replace("\n", "").replace("\r", "")
                                
                                try:
                                    description = (self.trim(description, 350, '...'))
                                except Exception,e:
                                    self.log("description Trim failed" + str(e))
                                    description = (description[:350])
                                    pass
                                    
                                try:
                                    subtitle = (self.trim(subtitle, 350, ''))
                                except Exception,e:
                                    self.log("subtitle Trim failed" + str(e))
                                    subtitle = (subtitle[:350])
                                    pass
                                
                                #skip old shows that have already ended
                                if now > stopDate:
                                    continue
                                
                                #adjust the duration of the current show
                                if now > startDate and now <= stopDate:
                                    try:
                                        dur = ((stopDate - startDate).seconds)
                                    except Exception,e:
                                        dur = 3600  #60 minute default
                                        
                                #use the full duration for an upcoming show
                                if now < startDate:
                                    try:
                                        dur = (stopDate - startDate).seconds
                                    except Exception,e:
                                        dur = 3600  #60 minute default
                                    
                                if type == 'tvshow':
                                    episodetitle = (('0' if seasonNumber < 10 else '') + str(seasonNumber) + 'x' + ('0' if episodeNumber < 10 else '') + str(episodeNumber) + ' - '+ (subtitle)).replace('  ',' ')

                                    if str(episodetitle[0:5]) == '00x00':
                                        episodetitle = episodetitle.split("- ", 1)[-1]
                                        
                                    tmpstr = str(dur) + ',' + title + "//" + episodetitle + "//" + description + "//" + genre + "//" + str(startDate) + "//" + LiveID + '\n' + setting2
                                
                                else: #Movie
                                    tmpstr = str(dur) + ',' + title + "//" + subtitle + "//" + description + "//" + genre + "//" + str(startDate) + "//" + LiveID + '\n' + setting2
                            
                                tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                                showList.append(tmpstr)
                                showcount += 1
                                
                                if showcount > limit:
                                    break

                                if self.background == False:
                                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding LiveTV, parsing " + chname, "added " + str(showcount) + " entries")
                    root.clear()   
                except:
                    pass
            f.close()                   
            if showcount == 0:
                self.log('Unable to find xmltv data for ' + setting1)
        except Exception,e:
            self.log("fillLiveTV Failed!" + str(e), xbmc.LOGERROR)
        return showList
        
            
    def fillLiveTVPVR(self, setting1, setting2, setting3, setting4, chname, limit):
        self.log("fillLiveTVPVR")
        showList = []
        showcount = 0
        json_query = ('{"jsonrpc":"2.0","method":"PVR.GetBroadcasts","params":{"channelid":%s,"properties":["title","plot","plotoutline","starttime","endtime","runtime","genre","episodename","episodenum","episodepart","firstaired","hastimer","parentalrating","thumbnail","rating"]}, "id": 1}' % setting1)
        json_folder_detail = self.sendJSON(json_query)
        detail = re.compile("{(.*?)}", re.DOTALL ).findall(json_folder_detail)
        now = self.parsePVRDate((str(datetime.datetime.utcnow())).split(".")[0])
        
        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding LiveTV, parsing " + chname)

        try:
            for f in detail:
                if self.threadPause() == False:
                    del showList[:]
                    return
                    
                titles = re.search('"title" *: *"(.*?)"', f)
                if titles:
                    title = titles.group(1)
                else:
                    try:
                        labels = re.search('"label" *: *"(.*?)"', f)
                        title = labels.group(1)
                    except:
                        title = None
                
                if title:
                    startDates = re.search('"starttime" *: *"(.*?)",', f)
                    stopDates = re.search('"endtime" *: *"(.*?)",', f)
                    subtitle = 'LiveTV'
                    Managed = False
                    id = 0
                    seasonNumber = 0
                    episodeNumber = 0
                    
                    if startDates:
                        startDate = self.parsePVRDate(startDates.group(1))
                        stopDate = self.parsePVRDate(stopDates.group(1))

                    if now > stopDate:
                        continue

                    runtimes = re.search('"runtime" *: *"(.*?)",', f)
                    #adjust the duration of the current show
                    if now > startDate and now <= stopDate:
                        if runtimes:
                            dur = int(runtimes.group(1)) * 60
                        else:
                            dur = int((stopDate - startDate).seconds)

                    #use the full duration for an upcoming show
                    if now < startDate:
                        if runtimes:
                            dur = int(runtimes.group(1)) * 60
                        else:
                            dur = ((stopDate - startDate).seconds)   
             
                    movie = False
                    genres = re.search('"genre" *: *"(.*?)",', f)
                    if genres:
                        genre = genres.group(1)
                        if genre.lower() == 'movie':
                            movie = True
                    else:
                        genre = 'Unknown'
                        
                    tvtypes = ['Episodic','Series','Sports','News','Paid Programming']
                    if dur >= 7200 and genre not in tvtypes:
                        movie = True
                        
                    if movie == True:
                        type = 'movie'
                    else:
                        type = 'tvshow'

                    try:
                        test = title.split(" *")[1]
                        title = title.split(" *")[0]
                        playcount = 0
                    except Exception,e:
                        playcount = 1
                        pass

                    plots = re.search('"plot" *: *"(.*?)"', f)
                    if plots:
                        description = plots.group(1)
                    else:
                        description = ''

                    ratings = re.search('"rating" *: *"(.*?)"', f)
                    if ratings:
                        rating = ratings.group(1)
                    else:
                        rating = 'NR'
                    
                    # if type == 'tvshow':
                        # episodenames = re.search('"episodename" *: *"(.*?)"', f)
                        # if episodename and len(episodenames) > 0:
                            # episodename = episodenames.group(1)
                        # else:
                            # episodename = ''
                        # episodenums = re.search('"episodenum" *: *"(.*?)"', f)
                        # if episodenums and len(episodenums) > 0:
                            # episodenum = episodenums.group(1) 
                        # else:
                            # episodenum = 0 
                        # episodeparts = re.search('"episodepart" *: *"(.*?)"', f)
                        # if episodeparts and len(episodeparts) > 0:
                            # episodepart = episodeparts.group(1)
                        # else:
                            # episodepart = 0 

                    #filter unwanted ids by title
                    if title == ('Paid Programming') or description == ('Paid Programming'):
                        ignoreParse = True
                    else:
                        ignoreParse = False
                                            
                    #Enable Enhanced Parsing
                    if REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true' and ignoreParse == False: 
                        if (((now > startDate and now <= stopDate) or (now < startDate))):
                            year = 0
                            if type == 'tvshow': 
                                tvdbid = 0                                     
                                try:
                                    year = (title.split(' ('))[1].replace(')','')
                                    title = (title.split(' ('))[0]
                                except:
                                    try:
                                        year = elem.findtext('date')[0:4]
                                    except:
                                        year = 0

                                year, id, genre, rating, Managed, tagline = self.getEnhancedGuideData(title, year, tvdbid, genre, rating, type)                                            
                            else:#Movie
                                imdbid = 0
                                try:
                                    year = (title.split(' ('))[1].replace(')','')
                                    title = (title.split(' ('))[0]
                                except:
                                    #Date element holds the original air date of the program
                                    try:
                                        year = elem.findtext('date')[0:4]
                                    except:
                                        year = 0
                                        
                                if subtitle == 'LiveTV':
                                    tagline = ''
                                    
                                year, id, genre, rating, Managed, subtitle = self.getEnhancedGuideData(title, year, imdbid, genre, rating, type, tagline)                                            

                    if seasonNumber > 0:
                        seasonNumber = '%02d' % int(seasonNumber)
                    
                    if episodeNumber > 0:
                        episodeNumber = '%02d' % int(episodeNumber)
                             
                    try:
                        description = (self.trim(description, 350, '...'))
                    except Exception,e:
                        self.log("description Trim failed" + str(e))
                        description = (description[:350])
                        pass
                            
                    GenreLiveID = [genre,type,id,0,Managed,playcount,rating] 
                    genre, LiveID = self.packGenreLiveID(GenreLiveID) 
                   
                    if type == 'tvshow':
                        episodetitle = (('0' if seasonNumber < 10 else '') + str(seasonNumber) + 'x' + ('0' if episodeNumber < 10 else '') + str(episodeNumber) + ' - '+ (subtitle)).replace('  ',' ')

                        if str(episodetitle[0:5]) == '00x00':
                            episodetitle = episodetitle.split("- ", 1)[-1]
                            
                        tmpstr = str(dur) + ',' + title + "//" + episodetitle + "//" + description + "//" + genre + "//" + str(startDate) + "//" + LiveID + '\n' + setting2
                    
                    else: #Movie
                        tmpstr = str(dur) + ',' + title + "//" + subtitle + "//" + description + "//" + genre + "//" + str(startDate) + "//" + LiveID + '\n' + setting2
                
                    tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                    showList.append(tmpstr)
                    showcount += 1
                    
                    if showcount > limit:
                        break
        
            if showcount == 0:
                self.log('Unable to find pvr guidedata for ' + setting1)
        except Exception: 
            pass
        return showList

        
    def buildInternetTVFileList(self, setting1, setting2, setting3, setting4, limit):
        self.log('buildInternetTVFileList')
        showList = []
        seasoneplist = []
        showcount = 0
        dur = 0
        LiveID = 'other|0|0|False|1|NR|'  
        
        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding InternetTV, parsing " + str(setting3))

        title = setting3
        description = setting4
        if not description:
            description = title
        istvshow = True
        # setting2 = (tidy(setting2)).replace(',', '')
        if setting1 != '':
            dur = setting1
        else:
            dur = 5400  #90 minute default
                
        self.log("buildInternetTVFileList, CHANNEL: " + str(self.settingChannel) + ", " + title + "  DUR: " + str(dur))
        tmpstr = str(dur) + ',' + title + "//" + "InternetTV" + "//" + description + "//" 'InternetTV' + "////" + LiveID + '\n' + setting2
        tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
        for i in range(limit):
            showList.append(tmpstr)
        return showList

        
    def createYoutubeFilelist(self, setting1, setting2, setting3, setting4, limit):
        self.log("createYoutubeFilelist")
        showList = []
        showcount = 0
        self.YT_showList = []
        
        YTMSG = setting1
        if self.youtube_ok != False:
            limit = int(limit)
            # if setting2 == '1' or setting2 == '3' or setting2 == '4':
            if setting2 == '1':
                YTMSG = 'Channel ' + setting1
                showList = self.getYoutubeVideos(1, setting1, '', limit, YTMSG)
            elif setting2 == '2':
                YTMSG = 'Playlist ' + setting1
                showList = self.getYoutubeVideos(2, setting1, '', limit, YTMSG)
            elif setting2 == '5':
                YTMSG = 'Search Querys'
            elif setting2 == '7':
                YTMSG = 'MultiTube Playlists'
                showList = self.BuildMultiYoutubeChannelNetwork(setting1, setting2, setting3, setting4, limit)
            elif setting2 == '8':
                YTMSG = 'MultiTube Channels'
                showList = self.BuildMultiYoutubeChannelNetwork(setting1, setting2, setting3, setting4, limit)
            elif setting2 == '31':
                YTMSG = 'Seasons Channel'
                showList = self.BuildseasonalYoutubeChannel(setting1, setting2, setting3, setting4, limit)    
        return showList

        
    def BuildseasonalYoutubeChannel(self, setting1, setting2, setting3, setting4, limit):
        self.log("BuildseasonalYoutubeChannel")
        tmpstr = ''
        showList = []
        genre_filter = [setting1.lower()]
        Playlist_List = 'http://raw.github.com/Lunatixz/pseudotv-live-community/master/youtube_playlists_networks.xml'
        
        try:
            f = open_url(Playlist_List)
            linesLST = f.readlines()
            f.close
        except:
            return
            
        for i in range(len(linesLST)):
            line = str(linesLST[i]).replace("\n","").replace('""',"")
            line = line.split("|")
        
            #If List Formatting is bad return
            if len(line) == 7:  
                genre = line[0]
                chtype = line[1]
                setting1 = (line[2]).replace(",","|")
                setting2 = line[3]
                setting3 = line[4]
                setting4 = line[5]
                channel_name = line[6]
                CHname = channel_name

                if genre.lower() in genre_filter:
                    channelList = setting1.split('|')
                    
                    for n in range(len(channelList)):
                        tmpstr = self.createYoutubeFilelist(channelList[n], '2', setting3, setting4, limit)
                        showList.extend(tmpstr) 
        
        return showList
    
    
    def BuildMultiYoutubeChannelNetwork(self, setting1, setting2, setting3, setting4, limit):
        self.log("BuildMultiYoutubeChannelNetwork")
        
        if setting2 == '7':
            channelList = setting1.split('|')
            tmpstr = ''
            showList = []
            
            for n in range(len(channelList)):
                self.YT_VideoCount = 0
                tmpstr = self.createYoutubeFilelist(channelList[n], '2', setting3, setting4, limit)
                showList.extend(tmpstr)     
        else:
            channelList = setting1.split('|')
            tmpstr = ''
            showList = []
            
            for n in range(len(channelList)):
                self.YT_VideoCount = 0
                tmpstr = self.createYoutubeFilelist(channelList[n], '1', setting3, setting4, limit)
                showList.extend(tmpstr)
                
        random.shuffle(showList)
        return showList[:limit]
    
    
    def parseYoutubeDuration(self, duration):
        self.log('parseYoutubeDuration')
        try:
            """ Parse and prettify duration from youtube duration format """
            DURATION_REGEX = r'P(?P<days>[0-9]+D)?T(?P<hours>[0-9]+H)?(?P<minutes>[0-9]+M)?(?P<seconds>[0-9]+S)?'
            NON_DECIMAL = re.compile(r'[^\d]+')
            duration_dict = re.search(DURATION_REGEX, duration).groupdict()
            converted_dict = {}
            # convert all values to ints, remove nones
            for a, x in duration_dict.iteritems():
                if x is not None:
                    converted_dict[a] = int(NON_DECIMAL.sub('', x))
            x = time.strptime(str(timedelta(**converted_dict)).split(',')[0],'%H:%M:%S')
            return int(self.__total_seconds__(datetime.timedelta(hours=x.tm_hour,minutes=x.tm_min,seconds=x.tm_sec)))
        except Exception,e:
            pass
    
    
    def getYoutubeMeta(self, YTID):
        self.log('getYoutubeMeta_Cache')
        if Primary_Cache_Enabled == True:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = parserYT.cacheFunction(self.getYoutubeMeta_NEW, YTID)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.getYoutubeMeta_NEW(YTID)
                pass
        else:
            result = self.getYoutubeMeta_NEW(YTID)
        if not result:
            result = []
        return result  
        
        
    def getYoutubeMeta_NEW(self, YTID):
        self.log('getYoutubeMeta_NEW ' + YTID)
        try:
            YT_URL_Video = ('https://www.googleapis.com/youtube/v3/videos?key=%s&id=%s&part=snippet,id,statistics,contentDetails' % (YT_API_KEY, YTID))
            f = request_url(YT_URL_Video)
            detail = re.compile("},(.*?)}", re.DOTALL ).findall(f)
            title = ''
            description = ''
            thumbnail = ''
            duration = 0
            Chname = ''
            Chcat = '31'
            
            for f in detail:
                items = re.search('"items" *:', f)
                titles = re.search('"title" *: *"(.*?)",', f)
                descriptions = re.search('"description" *: *"(.*?)",', f)
                durations = re.search('"duration" *: *"(.*?)",', f)
                thumbnails = re.search('"url" *: *"(.*?)",', f)
                Chnames = re.search('"channelTitle" *: *"(.*?)",', f)
                Chcats = re.search('"categoryId" *: *"(.*?)",', f)

                if durations:
                    duration = durations.group(1)
                    duration = self.parseYoutubeDuration(duration)
                if Chnames:
                    Chname = self.CleanLabels(Chnames.group(1))
                if Chcats:
                    Chcat = Chcats.group(1)
                    
                if items:
                    if titles:
                        title = self.CleanLabels(titles.group(1))
                    if descriptions:
                        description = self.CleanLabels(descriptions.group(1).replace('\n',' '))
                    if thumbnails:
                        thumbnail = thumbnails.group(1)
            if title:
                if not description:
                    description = title
                try:
                    description = (self.trim(description, 350, ''))
                except Exception,e:
                    self.log("description Trim failed" + str(e))
                    description = (description[:350])
                    pass
                    
                self.log("getYoutubeMeta_NEW, return")
                return [title, description, duration, thumbnail, Chname, int(Chcat)]
        except:
            pass

            
    def getYoutubeVideos(self, YT_Type, YT_ID, YT_NextPG, limit, YTMSG):
        self.log("getYoutubeVideos") 
        region = 'US' #todo
        lang = xbmc.getLanguage(xbmc.ISO_639_1)
        Last_YT_NextPG = YT_NextPG
        
        youtubeApiUrl = 'https://www.googleapis.com/youtube/v3/'
        youtubeChannelsApiUrl = (youtubeApiUrl + 'channels?key=%s&chart=mostPopular&regionCode=%s&hl=%s&' % (YT_API_KEY, region, lang))
        youtubeSearchApiUrl = (youtubeApiUrl + 'search?key=%s&chart=mostPopular&regionCode=%s&hl=%s&' % (YT_API_KEY, region, lang))
        youtubePlaylistApiUrl = (youtubeApiUrl + 'playlistItems?key=%s&chart=mostPopular&regionCode=%s&hl=%s&' % (YT_API_KEY, region, lang))
        requestParametersChannelId = (youtubeChannelsApiUrl + 'forUsername=%s&part=id' % (YT_ID))
        requestChannelVideosInfo = (youtubeSearchApiUrl + 'channelId=%s&part=id&order=date&pageToken=%s&maxResults=50' % (YT_ID, YT_NextPG))
        requestPlaylistInfo = (youtubePlaylistApiUrl+ 'part=snippet&maxResults=50&playlistId=%s&pageToken=%s' % (YT_ID, YT_NextPG))
        try:
            if YT_Type == 1:
                if YT_ID[0:2] != 'UC':
                    YT_URL_Search = requestParametersChannelId
                    f = request_url(YT_URL_Search)
                    YT_IDS = re.search('"id" *: *"(.*?)"', f)
                    if YT_IDS:
                        YT_ID = YT_IDS.group(1)
                        self.getYoutubeVideos(YT_Type, YT_ID, YT_NextPG, limit, YTMSG)
                else:
                    YT_URL_Search = requestChannelVideosInfo
            elif YT_Type == 2:
                YT_URL_Search = requestPlaylistInfo
                   
            if self.background == False:
                self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Youtube, parsing " + str(YTMSG))     
            try:
                f = (request_url(YT_URL_Search))
                detail = re.compile( "{(.*?)}", re.DOTALL ).findall(f)

                for f in detail:
                    if self.threadPause() == False:
                        del self.YT_showList[:]
                        break

                    VidIDS = re.search('"videoId" *: *"(.*?)"', f)
                    YT_NextPGS = re.search('"nextPageToken" *: *"(.*?)"', f)
                    if YT_NextPGS:
                        YT_NextPG = YT_NextPGS.group(1)
                        
                    if VidIDS:
                        VidID = VidIDS.group(1)
                        YT_Meta = self.getYoutubeMeta(VidID)
                        
                        if YT_Meta and YT_Meta[2] > 0:                        
                            cats = {0 : '',
                                1 : 'Action & Adventure',
                                2 : 'Animation & Cartoons',
                                3 : 'Classic TV',
                                4 : 'Comedy',
                                5: 'Drama',
                                6 : 'Home & Garden',
                                7 : 'News',
                                8 : 'Reality & Game Shows',
                                9 : 'Science & Tech',
                                10 : 'Science Fiction',
                                11 : 'Soaps',
                                13 : 'Sports',
                                14 : 'Travel',
                                16 : 'Entertainment',
                                17 : 'Documentary',
                                20 : 'Nature',
                                21 : 'Beauty & Fashion',
                                23 : 'Food',
                                24 : 'Gaming',
                                25 : 'Health & Fitness',
                                26 : 'Learning & Education',
                                27 : 'Foreign Language',}
                            try:
                                Genre = cats[YT_Meta[5]]
                            except:
                                Genre = 'Unknown'
                                
                            tmpstr = str(YT_Meta[2]) + ',' + YT_Meta[0] + '//' + "Youtube - " + YT_Meta[4] + "//" + YT_Meta[1] + "//" + Genre + "////" + 'youtube|0|'+VidID+'|False|1|NR|' + '\n' + self.youtube_ok + VidID
                            tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                            self.log("createYoutubeFilelist, CHANNEL: " + str(self.settingChannel) + ", " + YT_Meta[0] + "  DUR: " + str(YT_Meta[2]))
                            self.YT_showList.append(tmpstr)
                            self.YT_VideoCount += 1
                            
                            if self.background == False:
                                self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding %s Videos" % str(self.YT_VideoCount))
                                
                        if self.YT_VideoCount >= limit:
                            return self.YT_showList
                            
                if YT_NextPG == Last_YT_NextPG:
                    return self.YT_showList
                else:
                    if YT_NextPG and self.YT_VideoCount < limit:
                        self.YT_showList += self.getYoutubeVideos(YT_Type, YT_ID, YT_NextPG, limit, YTMSG)
            except:
                pass
        except:
            pass
        return self.YT_showList
        
    
    def createRSSFileList(self, setting1, setting2, setting3, setting4, limit):
        xbmc.log("createRSSFileList_Cache")
        if Primary_Cache_Enabled == True:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = RSSTV.cacheFunction(self.createRSSFileList_NEW, setting1, setting2, setting3, setting4, limit)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.createRSSFileList_NEW(setting1, setting2, setting3, setting4, limit)
                pass
        else:
            result = self.createRSSFileList_NEW(setting1, setting2, setting3, setting4, limit)
        if not result:
            result = []
        return result  
        
    
    def createRSSFileList_NEW(self, setting1, setting2, setting3, setting4, limit):
        self.log("createRSSFileList")
        showList = []
        seasoneplist = []
        showcount = 0
        runtime = 0
        genre = 'Unknown'
            
        inSet = False
        startIndex = 1
        self.log("createRSSFileList, RSS " + ", Limit = " + str(limit))
        rssfeed = setting1
        feed = feedparser.parse(rssfeed)

        for i in range(len(feed['entries'])):   
            if self.threadPause() == False:
                del showList[:]
                break
            try:
                showtitle = feed.channel.title
                showtitle = showtitle.replace(":", "")
                eptitle = feed.entries[i].title
                eptitle = eptitle.replace("/", "-")
                eptitle = eptitle.replace(":", " ")
                eptitle = eptitle.replace("\"", "")
                eptitle = eptitle.replace("?", "")
                
                try:
                    showtitle = (self.trim(showtitle, 350, ''))
                except Exception,e:
                    self.log("showtitle Trim failed" + str(e))
                    showtitle = (showtitle[:350])
                    pass
                showtitle = showtitle.replace('/','')
            
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding RSS, parsing " + showtitle)
                    
                try:
                    eptitle = (self.trim(eptitle, 350, ''))
                except Exception,e:
                    self.log("eptitle Trim failed" + str(e))
                    eptitle = (eptitle[:350])
                    
                if 'author_detail' in feed.entries[i]:
                    studio = feed.entries[i].author_detail['name']  
                else:
                    self.log("createRSSFileList, Invalid author_detail")  
                
                if REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true':  
                    # todo parse itune:image
                    if 'media_thumbnail' in feed.entries[i]:
                        thumburl = (feed.entries[i].media_thumbnail[0]['url']).replace('\n','').replace('\r','').replace('\t','')
                        thumburl = (thumburl.encode('base64')).replace('\n','').replace('\r','').replace('\t','')
                    else:
                        thumburl = '0'
                else:
                    thumburl = '0'
                    
                if thumburl == '0':
                    self.log("createRSSFileList, Invalid media_thumbnail")

                if not '<p>' in feed.entries[i].summary_detail.value:
                    epdesc = feed.entries[i]['summary_detail']['value']
                    head, sep, tail = epdesc.partition('<div class="feedflare">')
                    epdesc = head
                else:
                    epdesc = feed.entries[i]['subtitle']
                
                if epdesc == '':
                    epdesc = feed.entries[i]['blip_puredescription'] 
                
                if epdesc == '':
                    epdesc = eptitle
                    
                epdesc = epdesc.replace('\n', '').replace('<br />', '\n').replace('&apos;','').replace('&quot;','"')
                
                try:
                    epdesc = (self.trim(epdesc, 350, '...'))
                except Exception,e:
                    self.log("epdesc Trim failed" + str(e))
                    epdesc = (epdesc[:350])
                    
                epdesc = epdesc.replace('\n','')
                
                if 'media_content' in feed.entries[i]:
                    url = feed.entries[i].media_content[0]['url']
                else:
                    url = feed.entries[i].links[1]['href']
                
                try:
                    runtimex = feed.entries[i]['itunes_duration']
                except Exception,e:
                    runtimex = ''
                    pass

                try:
                    if runtimex == '':
                        runtimex = feed.entries[i]['blip_runtime']
                except Exception,e:
                    runtimex = ''
                    pass

                if runtimex == '':
                    runtimex = 1800
                
                try:
                    summary = feed.channel.subtitle
                    summary = summary.replace(":", "")
                except Exception,e:
                    pass
                
                if feed.channel.has_key("tags"):
                    genre = str(feed.channel.tags[0]['term'])
                
                try:
                    time = (str(feed.entries[i].published_parsed)).replace("time.struct_time", "")                        
                    showseason = [word for word in time.split() if word.startswith('tm_mon=')]
                    showseason = str(showseason)
                    showseason = showseason.replace("['tm_mon=", "")
                    showseason = showseason.replace(",']", "")
                    showepisodenum = [word for word in time.split() if word.startswith('tm_mday=')]
                    showepisodenum = str(showepisodenum)
                    showepisodenum = showepisodenum.replace("['tm_mday=", "")
                    showepisodenum = showepisodenum.replace(",']", "")
                    showepisodenuma = [word for word in time.split() if word.startswith('tm_hour=')]
                    showepisodenuma = str(showepisodenuma)
                    showepisodenuma = showepisodenuma.replace("['tm_hour=", "")
                    showepisodenuma = showepisodenuma.replace(",']", "")  
                    
                    if len(runtimex) > 4:
                        runtime = runtimex.split(':')[-2]
                        runtimel = runtimex.split(':')[-3]
                        runtime = int(runtime)
                        runtimel = int(runtimel)
                        runtime = runtime + (runtimel*60)
                    if not len(runtimex) > 4:
                        runtimex = int(runtimex)
                        runtime = round(runtimex/60.0)
                        runtime = int(runtime)
                except Exception,e:
                    pass
                
                if runtime >= 1:
                    duration = runtime
                else:
                    duration = 90
                    
                duration = round(duration*60.0)
                duration = int(duration)
                url = url.replace("&amp;amp;feature=youtube_gdata", "").replace("http://www.youtube.com/watch?hd=1&v=", self.youtube_ok).replace("http://www.youtube.com/watch?v=", self.youtube_ok)
                tmpstr = str(duration) + ',' + eptitle + "//" + "RSS - " + showtitle + "//" + epdesc + "//" + genre + "////" + 'rss|0|'+thumburl+'|False|1|NR|' + '\n' + url
                tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                self.log("createRSSFileList, CHANNEL: " + str(self.settingChannel) + ", " + eptitle + "  DUR: " + str(duration))
                showList.append(tmpstr)
                showcount += 1
                                    
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding %s Videos" % str(showcount))
                
                if showcount > limit:
                    break
            except Exception,e:
                pass
        return showList

     
    def MusicVideos(self, setting1, setting2, setting3, setting4, limit):
        self.log("MusicVideos")
        showList = []
        if setting1 == '1':
            self.log("MusicVideos - LastFM")
            msg_type = "Last.FM"
            PluginCHK = self.youtube_player()
            if PluginCHK != False:
                showList = self.lastFM(setting1, setting2, setting3, setting4, limit)
        elif setting1 == '2':
            self.log("MusicVideos - MyMusicTV")
            PluginCHK = self.plugin_ok('plugin.video.my_music_tv')
            if PluginCHK != False:
                msg_type = "My MusicTV"
                showList = self.myMusicTV(setting1, setting2, setting3, setting4, limit)
                
        return showList
    
    
    def lastFM(self, setting1, setting2, setting3, setting4, limit):
        xbmc.log("lastFM_Cache")
        if Primary_Cache_Enabled == True:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = lastfm.cacheFunction(self.lastFM_NEW, setting1, setting2, setting3, setting4, limit)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.lastFM_NEW(setting1, setting2, setting3, setting4, limit)
                pass
        else:
            result = self.lastFM_NEW(setting1, setting2, setting3, setting4, limit)
        if not result:
            result = []
        return result   
    
    
    def lastFM_NEW(self, setting1, setting2, setting3, setting4, limit):
        self.log("lastFM_NEW")
        # Sample xml output:
        # <clip>
            # <artist url="http://www.last.fm/music/Tears+for+Fears">Tears for Fears</artist>
            # <track url="http://www.last.fm/music/Tears+for+Fears/_/Everybody+Wants+to+Rule+the+World">Everybody Wants to Rule the World</track>
            # <url>http://www.youtube.com/watch?v=ST86JM1RPl0&amp;feature=youtube_gdata_player</url>
            # <duration>191</duration>
            # <thumbnail>http://i.ytimg.com/vi/ST86JM1RPl0/0.jpg</thumbnail>
            # <rating max="5">4.9660454</rating>
            # <stats hits="1" misses="4" />
        # </clip>
        showList = [] 
        LastFMList = []
        tmpstr = ''
        api = 'http://api.tv.timbormans.com/user/'+setting2+'/topartists.xml'
        duration = 0
        artist = ''
        track = ''
        url = ''
        thumburl = ''
        rating = 0
        eptitle = ''
        epdesc = ''
        showcount = 0
        
        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Last.FM ,User " + setting2)

        for n in range(limit):

            if self.threadPause() == False:
                del fileList[:]
                break
            
            try:
                file = open_url(api)
                self.log('file' + str(file))
                data = file.read()
                self.log('data' + str(data))
                file.close()
                dom = parseString(data)

                xmlartist = dom.getElementsByTagName('artist')[0].toxml()
                artist = xmlartist.replace('<artist>','').replace('</artist>','')
                artist = artist.rsplit('>', -1)
                artist = artist[1]
                # artist = str(artist)
                artist = self.uncleanString(artist)

                xmltrack = dom.getElementsByTagName('track')[0].toxml()
                track = xmltrack.replace('<track url>','').replace('</track>','')
                track = track.rsplit('>', -1)
                track = track[1]
                # track = str(track)
                track = self.uncleanString(track)

                xmlurl = dom.getElementsByTagName('url')[0].toxml()
                url = xmlurl.replace('<url>','').replace('</url>','')  
                url = url.replace("https://", "").replace("http://", "").replace("www.youtube.com/watch?v=", "").replace("&feature=youtube_gdata_player", "").replace("&amp;feature=youtube_gdata_player", "")

                xmlduration = dom.getElementsByTagName('duration')[0].toxml()
                duration = xmlduration.replace('<duration>','').replace('</duration>','')

                # xmlthumbnail = dom.getElementsByTagName('thumbnail')[0].toxml()
                # thumburl = xmlthumbnail.replace('<thumbnail>','').replace('</thumbnail>','')
                
                xmlrating = dom.getElementsByTagName('rating')[0].toxml()
                rating = xmlrating.replace('<rating>','').replace('</rating>','')
                rating = rating.rsplit('>', -1)
                rating = rating[1]
                rating = rating[0:4]
                eptitle = uni(artist + ' - ' + track)
                epdesc = uni('Rated ' + rating + '/5.00')
                
                tmpstr = str(duration) + ',' + eptitle + "//" + "Last.FM" + "//" + epdesc + "//" + 'Music' + "////" + 'youtube|0|'+url+'|False|1|NR|' + '\n' + self.youtube_ok + url
                tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                showList.append(tmpstr)
                showcount += 1    
    
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding %s Videos" % str(showcount))
            except Exception,e:
                pass    
                
        return showList

    
    def myMusicTV(self, setting1, setting2, setting3, setting4, limit):
        self.log("myMusicTV")
        path = xbmc.translatePath("special://profile/addon_data/plugin.video.my_music_tv/cache/plist")
        fle = os.path.join(path,setting2+".xml.plist")
        showcount = 0
        YTid = 0
        MyMusicLST = []
        type = 'musicvideo'
        
        try:
            if FileAccess.exists(fle):
                f = FileAccess.open(fle, "r")
                lineLST = f.readlines()
                f.close()
                
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding My MusicTV, parsing " + setting2)

                for n in range(len(lineLST)):
                    if self.threadPause() == False:
                        del fileList[:]
                        break
                        
                    line = lineLST[n].replace("['",'').replace("']",'').replace('["','').replace("\n",'')
                    line = line.split(", ")
                    title = line[0]
                    link = line[1].replace("'",'')
                    link = self.CleanPlayableFile(link)
                    
                    try:
                        id = str(os.path.split(link)[1]).split('?url=')[1]
                        source = str(id).split('&mode=')[1]
                        id = str(id).split('&mode=')[0]
                    except:
                        pass

                    try:
                        artist = title.split(' - ')[0]
                        track = title.split(' - ')[1].replace("'",'')
                    except:
                        artist = title
                        track = ''
                        pass
                    
                    # Parse each source for duration details todo
                    #if source == 'playVevo':
                        #playVevo()
                    # def playVevo(id):
                        # opener = urllib2.build_opener()
                        # userAgent = "Mozilla/5.0 (Windows NT 6.1; rv:30.0) Gecko/20100101 Firefox/30.0"
                        # opener.addheaders = [('User-Agent', userAgent)]
                        # content = opener.open("http://videoplayer.vevo.com/VideoService/AuthenticateVideo?isrc="+id).read()
                        # content = str(json.loads(content))
                        # print content
                        
                    if link.startswith('plugin://plugin.video.bromix.youtube') or mediapath.startswith('plugin://plugin.video.youtube'):
                        link = self.CleanPlayableFile(link)
                        YTid = link.split('id=')[1]
                        type = 'youtube'
                        
                    tmpstr = str(300) + ',' + artist + "//" + "My MusicTV" + "//" + track + "//" + 'Music' + "////" + type+'|0|'+YTid+'|False|1|NR|' + '\n' + link
                    tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                    MyMusicLST.append(tmpstr)
                    showcount += 1    
                    
                    if showcount > limit:
                        break

                    if self.background == False:
                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding %s Videos" % str(showcount))
            else:
                self.log("myMusicTV, No MyMusic plist cache found = " + str(fle))
                
        except Exception,e:  
            pass  
        return MyMusicLST

        
    def xmltv_ok(self, setting3):
        self.log("xmltv_ok, setting3 = " + str(setting3))
        self.xmltvValid = False
        if setting3.lower() == 'ptvlguide':
            if FileAccess.exists(PTVLXML):
                self.xmlTvFile = PTVLXML
                self.xmltvValid = True
        elif setting3[0:4] == 'http':
            self.xmlTvFile = setting3
            self.xmltvValid = self.url_ok(setting3)
        elif setting3.lower() == 'pvr':
            self.xmltvValid = True
        elif setting3.lower()  == 'zap2it':
            self.xmltvValid = True
        elif setting3.lower()  == 'scheduledirect':
            self.xmltvValid = True
        elif setting3 != '':
            self.xmlTvFile = xbmc.translatePath(os.path.join(REAL_SETTINGS.getSetting('xmltvLOC'), str(setting3) +'.xml'))
            if FileAccess.exists(self.xmlTvFile):
                self.xmltvValid = True          

        self.log("xmltvValid = " + str(self.xmltvValid))
        return self.xmltvValid
           
           
    def Valid_ok(self, setting2):
        self.log("Valid_ok_Cache")
        self.Override_ok = REAL_SETTINGS.getSetting('Override_ok') == "true"
        self.log('Override Stream Validation is ' + str(self.Override_ok))
        if Primary_Cache_Enabled == True and self.Override_ok == False:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = daily.cacheFunction(self.Valid_ok_NEW, setting2)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.Valid_ok_NEW(setting2)
                pass
        else:
            result = self.Valid_ok_NEW(setting2)
        if not result:
            result = False
        return result
        
        
    def Valid_ok_NEW(self, setting2):
        self.log("Valid_ok_NEW")
        self.Override_ok = REAL_SETTINGS.getSetting('Override_ok') == "true"        
        #plugin check  
        if setting2[0:6] == 'plugin':  
            return self.plugin_ok(setting2)  
        #Override Check# 
        elif self.Override_ok == True:
            return True
        #rtmp check
        elif setting2[0:4] == 'rtmp':
            return self.rtmpDump(setting2)      
        #http check     
        elif setting2[0:4] == 'http':
            return self.url_ok(setting2)
        #strm check  
        elif setting2[-4:] == 'strm':         
            return self.strm_ok(setting2)
        #pvr check
        elif setting2[0:3] == 'pvr':
            return True  
        #upnp check
        elif setting2[0:4] == 'upnp':
            return True 
        #udp check
        elif setting2[0:3] == 'udp':
            return True  
        #rtsp check
        elif setting2[0:4] == 'rtsp':
            return True  
        #HDHomeRun check
        elif setting2[0:9] == 'hdhomerun':
            return True  
  
  
    def strm_ok(self, setting2):
        self.log("strm_ok, " + str(setting2))
        self.strmFailed = False
        self.strmValid = False
        rtmpOK = True
        urlOK = True
        pluginOK = True
        lines = ''
        youtube_plugin = self.youtube_player()
             
        if youtube_plugin != False:
            fallback = (youtube_plugin + 'Y8WlAhpHzkM')
        else:
            fallback = ''

        try:
            f = FileAccess.open(setting2, "r")
            linesLST = f.readlines()
            self.log("strm_ok.Lines = " + str(linesLST))
            f.close()

            for i in range(len(set(linesLST))):
                lines = linesLST[i]
                self.strmValid = self.Valid_ok(lines)

                if self.strmValid == False:
                    self.log("strm_ok, failed strmCheck; writing fallback video")
                    f = FileAccess.open(setting2, "w")
                    for i in range(len(linesLST)):
                        lines = linesLST[i]
                        if lines != fallback:
                            f.write(lines + '\n')
                        self.logDebug("strm_ok, file write lines = " + str(lines))
                    f.write(fallback)
                    f.close()
                    self.strmValid = True 
                               
        except Exception,e:
            pass
        return self.strmValid   


    def getffprobeLength(filename):
        self.FFpath = self.OSpath.replace('rtmpdump','ffprobe')
        FFPROBE = xbmc.translatePath(os.path.join(ADDON_PATH, 'resources', 'lib', 'rtmpdump', self.FFpath))
        result = subprocess.Popen([FFPROBE, filename],
        stdout = subprocess.PIPE, stderr = subprocess.STDOUT)
        return [x for x in result.stdout.readlines() if "Duration" in x]
      
      
    def rtmpDump(self, stream):
        self.rtmpValid = False
        url = unquote(stream)
        RTMPDUMP = xbmc.translatePath(os.path.join(ADDON_PATH, 'resources', 'lib', 'rtmpdump', self.OSpath))
        self.log("RTMPDUMP = " + RTMPDUMP)
        assert os.path.isfile(RTMPDUMP)
        
        if "playpath" in url:
            url = re.sub(r'playpath',"-y playpath",url)
            self.logDebug("playpath url = " + str(url))
            command = [RTMPDUMP, '-B 1', '-m 2', '-r', url,'-o','test.flv']
            self.logDebug("RTMPDUMP command = " + str(command))
        else:
            command = [RTMPDUMP, '-B 1', '-m 2', '-r', url,'-o','test.flv']
            self.logDebug("RTMPDUMP command = " + str(command))
       
        CheckRTMP = Popen(command, shell=True, stdin=PIPE, stdout=PIPE, stderr=STDOUT)
        output = CheckRTMP.communicate()[0]
        
        if "ERROR: RTMP_ReadPacket" in output:
            self.log("rtmpDump, ERROR: RTMP_ReadPacket")
            self.rtmpValid = False 
        elif "ERROR: Problem accessing the DNS." in output:
            self.rtmpValid = False    
            self.log("rtmpDump, ERROR: Problem accessing the DNS.")
        elif "INFO: Connected..." in output:
            self.log("rtmpDump, INFO: Connected...")
            self.rtmpValid = True
        else:
            self.log("rtmpDump, ERROR?: Unknown response..." + str(output))
            self.rtmpValid = False
        
        self.log("rtmpValid = " + str(self.rtmpValid))
        return self.rtmpValid
        
                
    def url_ok(self, url):
        self.urlValid = False
        url = unquote(url)
        try: 
            request = urllib2.Request(url)
            request.get_method = lambda : 'HEAD'
            try:
                response = urllib2.urlopen(request)
                self.log("url_ok, INFO: Connected...")
                self.urlValid = True
            except urllib2.HTTPError:
                self.log("url_ok, ERROR: HTTP URL NOT VALID, ERROR: " + str(e))
                self.urlValid = False
        except:
            pass
        self.log("urlValid = " + str(self.urlValid))
        return self.urlValid
        

    def plugin_ok(self, plugin):
        self.log("plugin_ok, plugin = " + plugin)
        self.PluginFound = False
        self.Pluginvalid = False
        
        try:
            if plugin[0:9] == 'plugin://':
                plugin = plugin.replace("plugin://","")
                # addon = os.path.split(plugin)[0]
                # addon = (plugin.split('/?')[0]).replace("plugin://","")
                addon = splitall(plugin)[0]
                self.log("plugin id = " + addon)
            else:
                addon = plugin

            self.PluginFound = xbmc.getCondVisibility('System.HasAddon(%s)' % addon) == 1
            if self.PluginFound == True:
                
                if REAL_SETTINGS.getSetting("plugin_ok_level") == "0":#Low Check
                    self.Pluginvalid = True
                
                elif REAL_SETTINGS.getSetting("plugin_ok_level") == "1":#High Check
                    json_query = ('{"jsonrpc": "2.0", "method": "Files.GetDirectory", "params": {"directory":"%s"}, "id": 1}' % plugin)
                    json_folder_detail = self.sendJSON(json_query)
                    addon_detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_folder_detail)
                    
                    ## TODO ## Search for exact file, true if found.
                    for f in (addon_detail):
                        file = re.search('"file" *: *"(.*?)"', f)
                        
                    if file != None and len(file.group(1)) > 0:
                        self.Pluginvalid = True     
        except Exception,e:
            self.log("plugin_ok Failed!" + str(e), xbmc.LOGERROR)
             
        self.log("PluginFound = " + str(self.PluginFound))
        return self.Pluginvalid
                                
        
    def youtube_player(self):
        self.log("youtube_player")
        if self.plugin_ok('plugin.video.youtube') == True:
            path = 'plugin://plugin.video.youtube/?action=play_video&videoid='
            # path = 'plugin://plugin.video.bromix.youtube/play/?video_id='
        else:
            path = False
        return path
            
        
    def trim(self, content, limit, suffix):
        if len(content) <= limit:
            return content
        else:
            return content[:limit].rsplit(' ', 1)[0]+suffix

            
    def insertBCTfiles(self, channel, fileList, type):
        self.log("insertBCTfiles, channel = " + str(channel))
        bctFileList = []
        newFileList = []
        fileListNum = len(fileList)
        FileListMediaLST = []
        LiveID = 'tvshow|0|0|False|1|NR|'
        CommercialsType = REAL_SETTINGS.getSetting("commercials")
        
        chtype = (ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_type'))
        setting1 = (ADDON_SETTINGS.getSetting('Channel_' + str(channel) + '_1'))
        
        if chtype == '0':
            directory, filename = os.path.split(setting1)
            filename = (filename.split('.'))
            chname = (filename[0])
        else:
            chname = ADDON_SETTINGS.getSetting("Channel_" + str(channel) + "_1")  
        
        #Bumpers
        BumperNum = 0
        BumperLST = []
        BumpersType = REAL_SETTINGS.getSetting("bumpers")
        numBumpers = int(REAL_SETTINGS.getSetting("numbumpers")) + 1
        
        if BumpersType != "0" and type != 'movies': 
            BumperLST = self.GetBumperList(BumpersType, chname)
            
            if BumperLST and len(BumperLST) > 0:
                random.shuffle(BumperLST)
                
            BumperNum = len(BumperLST)
            self.log("insertBCTfiles, Bumpers.numBumpers = " + str(numBumpers))
        
        #Ratings
        if BumpersType!= "0" and type == 'movies' and REAL_SETTINGS.getSetting('bumperratings') == 'true':
            fileList = self.GetRatingList(chtype, chname, channel, fileList)

        #3D, insert "put glasses on" for 3D and use 3D ratings if enabled.
        if BumpersType!= "0" and type == 'movies' and REAL_SETTINGS.getSetting('bumper3d') == 'true':
            fileList = self.Get3DList(chtype, chname, channel, fileList)
            
        #Commercial
        CommercialNum = 0
        CommercialLST = []
        numCommercials = int(REAL_SETTINGS.getSetting("numcommercials")) + 1
        if CommercialsType != '0' and type != 'movies':
            CommercialLST = self.GetCommercialList(CommercialsType)
            
            if CommercialLST and len(CommercialLST) > 0:
                random.shuffle(CommercialLST)
            
            CommercialNum = len(CommercialLST)#number of Commercial items in full list
            self.log("insertBCTfiles, Commercials.numCommercials = " + str(numCommercials))
        
        #Trailers
        TrailerNum = 0
        TrailerLST = []
        TrailersType = REAL_SETTINGS.getSetting("trailers")
        trailersgenre = REAL_SETTINGS.getSetting("trailersgenre")
        trailersHDnetType = REAL_SETTINGS.getSetting("trailersHDnetType")
        trailerschannel = REAL_SETTINGS.getSetting("trailerschannel")
        numTrailers = int(REAL_SETTINGS.getSetting("numtrailers")) + 1
        
        if REAL_SETTINGS.getSetting('trailers') != '0':
            TrailerLST = self.GetTrailerList(chtype, chname, TrailersType, trailersgenre, trailersHDnetType, trailerschannel)
            if TrailerLST and len(TrailerLST) > 0:
                random.shuffle(TrailerLST)
            TrailerNum = len(TrailerLST)#number of trailer items in full list
            self.logDebug("insertBCTfiles, trailers.numTrailers = " + str(numTrailers))    

        for i in range(fileListNum):
            bctDur = 0
            bctFileList = []
            BumperMedia = ''
            BumperMediaLST = []
            CommercialMedia = ''
            CommercialMediaLST = []
            trailerMedia = ''
            trailerMediaLST = []
            File = ''
            
            if BumperNum > 0:
                for n in range(numBumpers):
                    if self.background == False:
                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Bumpers")
                    Bumper = random.choice(BumperLST)#random fill Bumper per show by user selected amount
                    BumperDur = int(Bumper.split(',')[0]) #duration of Bumper
                    bctDur += BumperDur
                    BumperMedia = Bumper.split(',', 1)[-1] #link of Bumper
                    BumperMedia = ('#EXTINF:' + str(BumperDur) + ',//////Bumper////' + LiveID + '\n' + uni(BumperMedia))
                    BumperMediaLST.append(BumperMedia)
            
            if CommercialNum > 0:
                for n in range(numCommercials):    
                    if self.background == False:
                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Commercials")
                    Commercial = random.choice(CommercialLST)#random fill Commercial per show by user selected amount
                    CommercialDur = int(Commercial.split(',')[0]) #duration of Commercial
                    bctDur += CommercialDur
                    CommercialMedia = Commercial.split(',', 1)[-1] #link of Commercial
                    CommercialMedia = ('#EXTINF:' + str(CommercialDur) + ',//////Commercial////' + LiveID + '\n' + uni(CommercialMedia))
                    CommercialMediaLST.append(CommercialMedia)

            if TrailerNum > 0:
                for n in range(numTrailers):    
                    if self.background == False:
                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Trailers")
                    trailer = random.choice(TrailerLST)#random fill trailers per show by user selected amount
                    trailerDur = int(trailer.split(',')[0]) #duration of trailer
                    bctDur += trailerDur
                    trailerMedia = trailer.split(',', 1)[-1] #link of trailer
                    trailerMedia = ('#EXTINF:' + str(trailerDur) + ',//////Trailer////' + LiveID + '\n' + uni(trailerMedia))
                    trailerMediaLST.append(trailerMedia)   

            bctFileList.extend(BumperMediaLST)
            bctFileList.extend(CommercialMediaLST)
            bctFileList.extend(trailerMediaLST)
            random.shuffle(bctFileList)       
            
            if len(bctFileList) > 0:                
                File = (fileList[i] + '\n')
            else: 
                File = fileList[i]
                
            File = uni(File + '\n'.join(bctFileList))
            newFileList.append(File)
           
        return newFileList
        
    
    def GetBumperList(self, BumpersType, chname):
        xbmc.log("GetBumperList_Cache")
        if Primary_Cache_Enabled == True:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = bumpers.cacheFunction(self.GetBumperList_NEW, BumpersType, chname)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.GetBumperList_NEW(BumpersType, chname)
                pass
        else:
            result = self.GetBumperList_NEW(BumpersType, chname)
        if not result:
            result = []
        return result  
    
    
    def GetBumperList_NEW(self, BumpersType, chname):
        BumperLST = []
        duration = 0
        
        #Local
        if BumpersType == "1":  
            self.log("GetBumperList_NEW, Local - " + chname)
            PATH = REAL_SETTINGS.getSetting('bumpersfolder')
            PATH = xbmc.translatePath(os.path.join(PATH,chname,''))
            self.log("GetBumperList_NEW, Local - PATH = " + PATH)
            
            if FileAccess.exists(PATH):
                try:
                    LocalBumperLST = []
                    LocalFLE = ''
                    LocalBumper = ''
                    LocalLST = self.walk(PATH)

                    for i in range(len(LocalLST)):    
                        if self.background == False:
                            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Local Bumpers")
                        filename = xbmc.translatePath(os.path.join(PATH,((LocalLST[i])[0])))
                        duration = self.videoParser.getVideoLength(filename)
                        if duration == 0:
                            duration = 3 
                        if duration > 0:
                            LocalBumper = (str(duration) + ',' + filename)
                            LocalBumperLST.append(LocalBumper)
                    BumperLST.extend(LocalBumperLST)                
                except: 
                    pass
        #Internet
        elif BumpersType == "2":
            self.log("GetBumperList_NEW - Internet")
            include = False
            self.vimeo_ok = self.plugin_ok('plugin://plugin.video.vimeo')
            
            if self.youtube_ok != False:
                try:
                    InternetBumperLST = []
                    duration = 3
                    Bumper_List = 'http://raw.github.com/Lunatixz/PseudoTV_Lists/master/bumpers.xml'
                    f = open_url_cached(Bumper_List)
                    linesLST = f.readlines()
                    f.close

                    for i in range(len(Bumper_List)):                        
                    
                        if self.background == False:
                            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding Internet Bumpers")
                        
                        lines = str(linesLST[i]).replace('\n','')
                        lines = lines.split('|')
                        ChannelName = lines[0]
                        BumperNumber = lines[1]
                        BumperSource = lines[2].split('_')[0]
                        BumperID = lines[2].split('_')[1]

                        if chname.lower() == ChannelName.lower():
                            if BumperSource == 'vimeo':
                                if self.vimeo_ok == True:
                                    include = True
                                    url = 'plugin://plugin.video.vimeo/?path=/root/video&action=play_video&videoid=' + BumperID
                            elif BumperSource == 'youtube':
                                if self.youtube_ok != False:
                                    include = True
                                    url = self.youtube_ok + BumperID

                            if include == True:
                                InternetBumper = (str(duration) + ',' + url)
                                InternetBumperLST.append(InternetBumper)
                    BumperLST.extend(InternetBumperLST)#Put local bumper list into master bumper list.                
                except: 
                    pass
        return BumperLST   
        

    def GetRatingList(self, chtype, chname, channel, fileList):
        self.log("GetRatingList_NEW")
        newFileList = []
        
        if self.youtube_ok != False:
            URL = self.youtube_ok + 'qlRaA8tAfc0'
            Ratings = (['NR','qlRaA8tAfc0'],['R','s0UuXOKjH-w'],['NC-17','Cp40pL0OaiY'],['PG-13','lSg2vT5qQAQ'],['PG','oKrzhhKowlY'],['G','QTKEIFyT4tk'],['18','g6GjgxMtaLA'],['16','zhB_xhL_BXk'],['12','o7_AGpPMHIs'],['6','XAlKSm8D76M'],['0','_YTMglW0yk'])

            for i in range(len(fileList)):
                file = fileList[i]
                lineLST = (fileList[i]).split('movie|')[1]
                mpaa = (lineLST.split('\n')[0]).split('|')[4]
                
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Ratings: " + str(mpaa))
                                
                for i in range(len(Ratings)):
                    rating = Ratings[i]        
                    if mpaa == rating[0]:
                        ID = rating[1]
                        URL = self.youtube_ok + ID
                
                tmpstr = '7,//////Rating////' + 'movie|0|0|False|1|'+str(mpaa)+'|' + '\n' + (URL) + '\n' + '#EXTINF:' + file
                newFileList.append(tmpstr)

        return newFileList
    
    
    def GetCommercialList(self, CommercialsType):   
        CommercialLST = []
        duration = 0
        channel = self.settingChannel
        
        if self.limit == 0 or self.limit > 200:
            limit = 200
        elif self.limit < 25:
            limit = 25
        else:
            limit = self.limit
            
        #Youtube - As Seen On TV
        if REAL_SETTINGS.getSetting('AsSeenOn') == 'true' and CommercialsType != '0':
            self.log("GetCommercialList_NEW, AsSeenOn")
            try:
                AsSeenOnCommercialLST = []          
                YoutubeLST = self.createYoutubeFilelist('PL_ikfJ-FJg77ioZ9nPuhJxuMe9GKu7plT|PL_ikfJ-FJg774gky7eu8DroAqCR_COS79|PL_ikfJ-FJg75N3Gn6DjL0ZArAcfcGigLY|PL_ikfJ-FJg765O5ppOPGTpQht1LwXmck4|PL_ikfJ-FJg75wIMSXOTdq0oMKm63ucQ_H|PL_ikfJ-FJg77yht1Z6Xembod33QKUtI2Y|PL_ikfJ-FJg77PW8AJ3yk5HboSwWatCg5Z|PL_ikfJ-FJg75v4dTW6P0m4cwEE4-Oae-3|PL_ikfJ-FJg76zae4z0TX2K4i_l5Gg-Flp|PL_ikfJ-FJg74_gFvBqCfDk2E0YN8SsGS8|PL_ikfJ-FJg758W7GVeTVZ4aBAcCBda63J', '7', '100', '1', limit)
                for i in range(len(YoutubeLST)): 
                
                    if self.background == False:
                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding AsSeenOnTV Commercials")

                    Youtube = YoutubeLST[i]
                    duration = Youtube.split(',')[0]
                    Commercial = Youtube.split('\n', 1)[-1]
                    
                    if Commercial != '' or Commercial != None:
                        AsSeenOnCommercial = (str(duration) + ',' + Commercial)
                        AsSeenOnCommercialLST.append(AsSeenOnCommercial)
                CommercialLST.extend(AsSeenOnCommercialLST)
            except Exception,e:
                self.log("GetCommercialList_NEW Failed!" + str(e), xbmc.LOGERROR)
        
        #Local
        if CommercialsType == '1':
            self.log("GetCommercialList_NEW, Local") 
            PATH = REAL_SETTINGS.getSetting('commercialsfolder')
            PATH = xbmc.translatePath(os.path.join(PATH,''))
            self.log("GetCommercialList_NEW, Local - PATH = " + PATH)
            
            if FileAccess.exists(PATH): 
                try:
                    LocalCommercialLST = []
                    LocalFLE = ''
                    LocalCommercial = ''
                    LocalLST = self.walk(PATH)
                    
                    for i in range(len(LocalLST)):    
                        if self.background == False:
                            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Local Commercials")
                        
                        filename = xbmc.translatePath(os.path.join(PATH,((LocalLST[i])[0])))
                        duration = self.videoParser.getVideoLength(filename)
                        
                        if duration == 0:
                            duration = 30
                        
                        if duration > 0:
                            LocalCommercial = (str(duration) + ',' + filename)
                            LocalCommercialLST.append(LocalCommercial)
                    
                    CommercialLST.extend(LocalCommercialLST)      
                except Exception,e:
                    self.log("GetCommercialList_NEW Failed!" + str(e), xbmc.LOGERROR)
                    
        #Youtube
        elif CommercialsType == '2':
            self.log("GetCommercialList_NEW, Youtube") 
            try:
                YoutubeCommercialLST = []
                YoutubeCommercial = REAL_SETTINGS.getSetting('commercialschannel') # info,type,limit
                YoutubeCommercial = YoutubeCommercial.split(',')    
                setting1 = YoutubeCommercial[0]
                setting2 = YoutubeCommercial[1]
                setting3 = YoutubeCommercial[2]
                setting4 = YoutubeCommercial[3]
                YoutubeLST = self.createYoutubeFilelist(setting1, setting2, setting3, setting4, limit)
                
                for i in range(len(YoutubeLST)):    
                    if self.background == False:
                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Youtube Commercials")
                    
                    Youtube = YoutubeLST[i]
                    duration = Youtube.split(',')[0]
                    Commercial = Youtube.split('\n', 1)[-1]
                    
                    if Commercial != '' or Commercial != None:
                        YoutubeCommercial = (str(duration) + ',' + Commercial)
                        YoutubeCommercialLST.append(YoutubeCommercial)
                
                CommercialLST.extend(YoutubeCommercialLST)
            except Exception,e:
                self.log("GetCommercialList_NEW Failed!" + str(e), xbmc.LOGERROR)
                
        #Internet (advertolog.com, ispot.tv)
        elif CommercialsType == '3' and isDon() == True:
            self.log("GetCommercialList_NEW, Internet") 
            Advertolog = REAL_SETTINGS.getSetting("Advertolog")
            Advertolog_Region = REAL_SETTINGS.getSetting("Advertolog_Region")
            Advertolog_Resolution = REAL_SETTINGS.getSetting("Advertolog_Resolution")
            iSpot_type = REAL_SETTINGS.getSetting("iSpot_type")
        
            try:
                InternetCommercialLST = []
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Internet Commercials")
                InternetCommercialLST = InternetCommercial(Advertolog, Advertolog_Region, Advertolog_Resolution, iSpot_type)
                CommercialLST.extend(InternetCommercialLST)  
            except Exception,e:
                self.log("GetCommercialList_NEW Failed!" + str(e), xbmc.LOGERROR)
           
        return CommercialLST 
   
   
    def GetTrailerList(self, chtype, chname, TrailersType, trailersgenre, trailersHDnetType, trailerschannel):
        xbmc.log("GetTrailerList_Cache")
        if Primary_Cache_Enabled == True:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = trailers.cacheFunction(self.GetTrailerList_NEW, chtype, chname, TrailersType, trailersgenre, trailersHDnetType, trailerschannel)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.GetTrailerList_NEW(chtype, chname, TrailersType, trailersgenre, trailersHDnetType, trailerschannel)
                pass
        else:
            result = self.GetTrailerList_NEW(chtype, chname, TrailersType, trailersgenre, trailersHDnetType, trailerschannel)
        if not result:
            result = []
        return result   
    
    
    def GetTrailerList_NEW(self, chtype, chname, TrailersType, trailersgenre, trailersHDnetType, trailerschannel):
        self.log("GetTrailerList_NEW")
        TrailerLST = []
        duration = 0
        genre = ''
        channel = self.settingChannel
        
        if chtype == '3' or chtype == '4' or chtype == '5':
            GenreChtype = True
        else:
            GenreChtype = False

        #Local
        if TrailersType == '1': 
            PATH = REAL_SETTINGS.getSetting('trailersfolder')
            PATH = xbmc.translatePath(os.path.join(PATH,''))
            self.log("GetTrailerList_NEW, Local - PATH = " + PATH)
            
            if FileAccess.exists(PATH):
                try:
                    LocalTrailerLST = []
                    LocalFLE = ''
                    LocalTrailer = ''
                    LocalLST = self.walk(PATH)
                    
                    for i in range(len(LocalLST)):    
                        
                        if self.background == False:
                            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Local Trailers")
                        
                        LocalFLE = LocalLST[i]
                        
                        if '-trailer' in LocalFLE:
                            duration = self.videoParser.getVideoLength(LocalFLE)
                            
                            if duration == 0:
                                duration = 120
                        
                            if duration > 0:
                                LocalTrailer = (str(duration) + ',' + LocalFLE)
                                LocalTrailerLST.append(LocalTrailer)
                                
                    TrailerLST.extend(LocalTrailerLST)                
                except Exception,e:
                    self.log("GetTrailerList_NEW Failed!" + str(e), xbmc.LOGERROR)
                    
        #XBMC Library - Local Json
        if TrailersType == '2':
            self.log("GetTrailerList_NEW, Local Json")
            JsonTrailerLST = []
            json_query = ('{"jsonrpc":"2.0","method":"VideoLibrary.GetMovies","params":{"properties":["genre","trailer","runtime"]}, "id": 1}')
            genre = ascii(chname)
            if self.youtube_ok != False:
                try:
                    if not self.cached_json_detailed_trailers:
                        self.logDebug('GetTrailerList, json_detail creating cache')
                        self.cached_json_detailed_trailers = self.sendJSON(json_query)   
                    json_detail = self.cached_json_detailed_trailers.encode('utf-8')   
                    self.logDebug('GetTrailerList, json_detail using cache')

                    if REAL_SETTINGS.getSetting('trailersgenre') == 'true' and GenreChtype == True:
                        JsonLST = ascii(json_detail.split("},{"))
                        match = [s for s in JsonLST if genre in s]
                        
                        for i in range(len(match)):    
                            if self.background == False:
                                self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Library Genre Trailers")
                            duration = 120
                            json = (match[i])
                            trailer = json.split(',"trailer":"',1)[-1]
                            if ')"' in trailer:
                                trailer = trailer.split(')"')[0]
                            else:
                                trailer = trailer[:-1]
                            
                            if trailer != '' or trailer != None or trailer != '"}]}':
                                if 'http://www.youtube.com/watch?hd=1&v=' in trailer:
                                    trailer = trailer.replace("http://www.youtube.com/watch?hd=1&v=", self.youtube_ok).replace("http://www.youtube.com/watch?v=", self.youtube_ok)
                                JsonTrailer = (str(duration) + ',' + trailer)
                                if JsonTrailer != '120,':
                                    JsonTrailerLST.append(JsonTrailer)
                        TrailerLST.extend(JsonTrailerLST)
                    else:
                        JsonLST = (json_detail.split("},{"))
                        match = [s for s in JsonLST if 'trailer' in s]
                        for i in range(len(match)):    
                            if self.background == False:
                                self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Library Trailers")
                            duration = 120
                            json = (match[i])
                            trailer = json.split(',"trailer":"',1)[-1]
                            if ')"' in trailer:
                                trailer = trailer.split(')"')[0]
                            else:
                                trailer = trailer[:-1]
                            if trailer != '' or trailer != None or trailer != '"}]}':
                                if 'http://www.youtube.com/watch?hd=1&v=' in trailer:
                                    trailer = trailer.replace("http://www.youtube.com/watch?hd=1&v=", self.youtube_ok).replace("http://www.youtube.com/watch?v=", self.youtube_ok)
                                JsonTrailer = (str(duration) + ',' + trailer)
                                if JsonTrailer != '120,':
                                    JsonTrailerLST.append(JsonTrailer)
                        TrailerLST.extend(JsonTrailerLST)     
                except Exception,e:
                    self.log("GetTrailerList_NEW Failed!" + str(e), xbmc.LOGERROR)
                    
        #Youtube
        if TrailersType == '3':
            self.log("GetTrailerList_NEW, Youtube")
            try:
                YoutubeTrailerLST = []
                YoutubeTrailers = REAL_SETTINGS.getSetting('trailerschannel') # info,type,limit
                YoutubeTrailers = YoutubeTrailers.split(',')
                setting1 = YoutubeTrailers[0]
                setting2 = YoutubeTrailers[1]
                setting3 = YoutubeTrailers[2]
                setting4 = YoutubeTrailers[3]     
                YoutubeLST = self.createYoutubeFilelist(setting1, setting2, setting3, setting4, '200')
                
                for i in range(len(YoutubeLST)):    
                    
                    if self.background == False:
                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Youtube Trailers")
                    
                    Youtube = YoutubeLST[i]
                    duration = Youtube.split(',')[0]
                    trailer = Youtube.split('\n', 1)[-1]
                    
                    if trailer != '' or trailer != None:
                        YoutubeTrailer = (str(duration) + ',' + trailer)
                        YoutubeTrailerLST.append(YoutubeTrailer)
                TrailerLST.extend(YoutubeTrailerLST)
            except Exception,e:
                self.log("GetTrailerList_NEW Failed!" + str(e), xbmc.LOGERROR)
                
        #Internet
        if TrailersType == '4' and isDon() == True:
            self.log("GetTrailerList_NEW, Internet")
            try:   
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(channel), "adding Internet Trailers")
                TrailerLST = InternetTrailer()
            except Exception,e:
                self.log("GetTrailerList_NEW Failed!" + str(e), xbmc.LOGERROR)

        return TrailerLST

        
    # Adapted from Ronie's screensaver.picture.slideshow * https://github.com/XBMC-Addons/screensaver.picture.slideshow/blob/master/resources/lib/utils.py    
    def walk(self, path):     
        self.log("walk " + path)
        VIDEO_TYPES = ('.avi', '.mp4', '.m4v', '.3gp', '.3g2', '.f4v', '.mov', '.mkv', '.flv', '.ts', '.m2ts', '.strm')
        video = []
        folders = []
        # multipath support
        if path.startswith('multipath://'):
            # get all paths from the multipath
            paths = path[12:-1].split('/')
            for item in paths:
                folders.append(urllib.unquote_plus(item))
        else:
            folders.append(path)
        for folder in folders:
            if FileAccess.exists(xbmc.translatePath(folder)):
                # get all files and subfolders
                dirs,files = xbmcvfs.listdir(os.path.join(folder,''))
                # natural sort
                convert = lambda text: int(text) if text.isdigit() else text
                alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
                files.sort(key=alphanum_key)
                for item in files:
                    # filter out all video
                    if os.path.splitext(item)[1].lower() in VIDEO_TYPES:
                        video.append([os.path.join(folder,item), ''])
                for item in dirs:
                    # recursively scan all subfolders
                    video += self.walk(os.path.join(folder,item,'')) # make sure paths end with a slash
        return video
        
    def extras(self, setting1, setting2, setting3, setting4, channel):
        self.log("extras")
        limit = MEDIA_LIMIT[int(REAL_SETTINGS.getSetting('MEDIA_LIMIT'))]
        showList = []

        if isDon() == True:  
            if setting1.lower() == 'popcorn':
                
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "Parsing Bringthepopcorn Movies, Please Wait...")
                
                showList = Bringpopcorn(setting2, setting3, setting4, channel)
                
            elif setting1.lower() == 'cinema':
                flename = self.createCinemaExperiencePlaylist()        
                if setting2 != flename:
                    flename == (xbmc.translatePath(setting2))             
                
                PrefileList = self.buildFileList(flename, channel, limit)
                
                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "Populating the PseudoCinema Experience, Please Wait...")
                
                showList = BuildCinemaExperienceFileList(setting1, setting2, setting3, setting4, channel, PrefileList)

        return showList


    #return plugin query, not tmpstr
    def PluginQuery(self, path): 
        self.log("PluginQuery") 
        json_folder_detail = ''
        FleType = 'video'
        json_query = uni('{"jsonrpc": "2.0", "method": "Files.GetDirectory", "params": {"directory": "%s", "media": "%s", "properties":["title","year","mpaa","imdbnumber","description","thumbnail","season","episode","playcount","genre","duration","runtime","showtitle","album","artist","plot","plotoutline","tagline"]}, "id": 1}' % (self.escapeDirJSON(path), FleType))
        json_folder_detail = self.sendJSON(json_query)
        return re.compile( "{(.*?)}", re.DOTALL ).findall(json_folder_detail)
    
    
    #Parse Plugin, return essential information. Not tmpstr
    def PluginInfo(self, path):
        self.log("PluginInfo") 
        json_query = uni('{"jsonrpc":"2.0","method":"Files.GetDirectory","params":{"directory":"%s","properties":["genre","runtime","description"]},"id":1}' % ( (path),))
        json_folder_detail = self.sendJSON(json_query)
        file_detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_folder_detail)
        Detail = ''
        DetailLST = []
        PluginName = os.path.split(path)[0]

        #run through each result in json return
        for f in (file_detail):
            filetype = re.search('"filetype" *: *"(.*?)"', f)
            label = re.search('"label" *: *"(.*?)"', f)
            genre = re.search('"genre" *: *"(.*?)"', f)
            runtime = re.search('"runtime" *: *([0-9]*?),', f)
            description = re.search('"description" *: *"(.*?)"', f)
            file = re.search('"file" *: *"(.*?)"', f)

            #if core values have info, proceed
            if filetype and file and label:
                filetype = filetype.group(1)
                title = (label.group(1)).replace(',',' ')
                file = file.group(1)

                try:
                    genre = genre.group(1)
                except:
                    genre = 'Unknown'
                    pass

                if genre == '':
                    genre = 'Unknown'

                try:
                    runtime = runtime.group(1)
                except:
                    runtime = 0
                    pass

                if runtime == 0 or runtime == '':
                    runtime = 1800

                try:
                    description = (description.group(1)).replace(',',' ')
                except:
                    description = PluginName
                    pass

                if description == '':
                    description = PluginName

                if title != '':
                    Detail = ((filetype + ',' + title + ',' + genre + ',' + str(runtime) + ',' + description + ',' + file)).replace(',,',',')
                    DetailLST.append(Detail)
                    
        # Stop playback from plugins
        if self.background == False:
            json_query = '{"jsonrpc":"2.0","method":"Input.ExecuteAction","params":{"action":"stop"},"id":1}'
            self.sendJSON(json_query); 
            
        return DetailLST
    
 
    # def BuildPluginFileList(self, setting1, setting2, setting3, setting4, limit):
        # xbmc.log("BuildPluginFileList_Cache")
        # if Primary_Cache_Enabled == True: 
            # try:
                # result = pluginTV.cacheFunction(self.BuildPluginFileList_NEW, setting1, setting2, setting3, setting4, limit)
            # except:
                # result = self.BuildPluginFileList_NEW(setting1, setting2, setting3, setting4, limit)
                # pass
        # else:
            # result = self.BuildPluginFileList_NEW(setting1, setting2, setting3, setting4, limit)
        # if not result:
            # result = []
        # return result  
        

    def BuildPluginFileList(self, setting1, setting2, setting3, setting4, limit, walk=True):
        self.log('BuildPluginFileList_NEW')
        showList = []
        DetailLST = []
        DetailLST_CHK = []
        PluginPathLst = []
        self.dircount = 0
        self.filecount = 0
        channel = self.settingChannel
        
        if setting1.endswith('/'):
            setting1 = setting1[:-1]

        try:
            Directs = (setting1.split('/')) # split folders
            Directs = ([x.replace('%2F','/') for x in Directs if x != '']) # remove empty elements, replace '%2F' with '/'
            plugins = Directs[1] # element 1 in split is plugin name
            Directs = Directs[2:]# slice two unwanted elements. ie (plugin:, plugin name)
            plugin = 'plugin://' + plugins
            PluginPath = (plugins.replace('plugin://','')).split('/')[0]
            PluginName = (xbmcaddon.Addon(id=PluginPath)).getAddonInfo('name')
            
            if len(Directs) == 0:
                lastfolder = PluginName
            else:
                DirectCount = len(Directs)
                lastfolder = Directs[DirectCount-1]
        except:
            return
            
        self.log('BuildPluginFileList_NEW, Directs = ' + str(Directs))
        
        try:
            excludeLST = setting2.split(',')
            excludeLST = ([x.lower() for x in excludeLST if x != '']) # remove empty elements
        except:
            excludeLST = []
            pass
            
        
        #filter out unwanted folders
        excludeLST += EX_FILTER
        self.log('BuildPluginFileList_NEW, excludeLST = ' + str(excludeLST))
        
        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "Building PluginTV", "Parsing " + (PluginName))

        Match = True
        while Match:

            DetailLST = self.PluginInfo(plugin)

            #Plugin listitems return parent list during error, catch repeat list and end loops.
            if DetailLST_CHK == DetailLST:
                break
            else:
                DetailLST_CHK = DetailLST

            #end while when no more directories to walk
            if len(Directs) <= 1:
                Match = False
                
            try:
                for i in range(len(DetailLST)):
                    
                    if self.background == False:
                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "Parsing " + (PluginName) + '/' + (lastfolder))
                        
                    Detail = (DetailLST[i]).split(',')
                    filetype = Detail[0]
                    title = Detail[1]
                    title = self.CleanLabels(title)
                    genre = Detail[2]
                    dur = Detail[3]
                    description = Detail[4]
                    file = Detail[5]
                                     
                    if filetype == 'directory':
                        CurDirect = self.CleanLabels(Directs[0])
                        if CurDirect.lower() == title.lower():
                            self.log('BuildPluginFileList_NEW, Directory Match: ' + CurDirect.lower() + ' = ' + title.lower())
                            PluginPathLst.append(file)
                            Directs.pop(0) #remove old directory, search next element
                            plugin = file
                            break
            except Exception,e:
                self.log("BuildPluginFileList_NEW, Failed! " + str(e))
             
        if walk:
            #all directories waled, parse final folder
            if len(Directs) == 0:              
                showList = self.PluginWalk(lastfolder, plugin, excludeLST, limit) 
            return showList
        else:
            return PluginPathLst.reverse()
           

    def BuildUPNPFileList(self, setting1, setting2, setting3, setting4, limit):
        self.log("BuildUPNPFileList_Cache")
        if Primary_Cache_Enabled == True:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = upnpTV.cacheFunction(self.BuildUPNPFileList_NEW, setting1, setting2, setting3, setting4, limit)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.BuildUPNPFileList_NEW(setting1, setting2, setting3, setting4, limit)
                pass
        else:
            result = self.BuildUPNPFileList_NEW(setting1, setting2, setting3, setting4, limit)
        if not result:
            result = []
        return result  
        
 
    def BuildUPNPFileList_NEW(self, setting1, setting2, setting3, setting4, limit):
        self.log('BuildUPNPFileList_NEW')  
        showList = []
        DetailLST = []
        DetailLST_CHK = []
        self.dircount = 0
        self.filecount = 0
        
        #filter out unwanted folders             
        try:
            excludeLST = setting2.split(',')
            excludeLST = ([x.lower() for x in excludeLST if x != '']) # remove empty elements
        except:
            excludeLST = []
        excludeLST += EX_FILTER           
        self.log('BuildUPNPFileList_NEW, excludeLST = ' + str(excludeLST))
        upnpID = setting1
        
        try:
            Directs = (setting1.split('/')) # split folders
            Directs = ([x.replace('%2F','/') for x in Directs if x != '']) # remove empty elements
            PluginName = Directs[0]
            Directs = Directs[2:]# slice two unwanted elements. ie (plugin:, plugin name)
        except:
            Directs = []
            PluginName = setting1

        self.log('BuildUPNPFileList_NEW, Directs = ' + str(Directs))

        if self.background == False:
            self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), 'parsing ' + str(PluginName))

        Match = True
        while Match:
            DetailLST = self.PluginInfo(upnpID)
            
            # Plugin listitems return parent list during error, catch repeat list and break loop.
            if DetailLST_CHK == DetailLST:
                break
            else:
                DetailLST_CHK = DetailLST

            # End while when no more directories to walk
            if len(Directs) <= 1:
                Match = False
                lastfolder = PluginName
                
            # Walk upnp source till matching directory found, then send to pluginwalk
            try:
                for i in range(len(DetailLST)):
                    Detail = (DetailLST[i]).split(',')
                    filetype = Detail[0]
                    title = self.CleanLabels(Detail[1])
                    genre = Detail[2]
                    dur = Detail[3]
                    description = Detail[4]
                    file = Detail[5]
                                                                         
                    if filetype == 'directory':
                        lastfolder = Directs[0]
                        if Directs[0].lower() == title.lower():
                            self.log('BuildUPNPFileList_NEW, Directory Match: ' + Directs[0].lower() + ' = ' + title.lower())
                            Directs.pop(0) #remove old directory, search next element
                            upnpID = file
                            break
            except Exception,e:
                self.log("BuildUPNPFileList_NEW, Failed! " + str(e))
  
        #all directories found, walk final folder
        if len(Directs) == 0:
            showList = self.PluginWalk(lastfolder, upnpID, excludeLST, limit, 'UPNP', 'video')
        return showList
    
    
    #recursively walk through plugin directories, return tmpstr of all files found.
    def PluginWalk(self, foldername, path, excludeLST, limit, xType='Plugin', FleType='video', ):
        self.log("PluginWalk")
        file_detail_CHK = []
        dirlimit = limit
        tmpstr = ''
        LiveID = 'tvshow|0|0|False|1|NR|'
        fileList = []
        dirs = []
        Managed = False
        PluginPath = (path.replace('plugin://','')).split('/')[0]
        PluginName = (xbmcaddon.Addon(id=PluginPath)).getAddonInfo('name')
        channel = self.settingChannel
        json_query = uni('{"jsonrpc": "2.0", "method": "Files.GetDirectory", "params": {"directory": "%s", "media": "%s", "properties":["title","year","mpaa","imdbnumber","description","season","episode","playcount","genre","duration","runtime","showtitle","album","artist","plot","plotoutline","tagline"]}, "id": 1}' % ((path), FleType))
        json_folder_detail = self.sendJSON(json_query)
        file_detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_folder_detail)                                  
        self.logDebug("PluginWalk, PluginPath = " + PluginPath)
        
        #Plugin listitems return parent list during error, catch repeat list and break loop.
        if file_detail_CHK == file_detail:
            return
        else:
            file_detail_CHK = file_detail
            
        try:
            if xType.lower() == 'upnp':
                xName = (path.split('/')[3]).split('-')[0]
            else:
                xName = PluginName

            #run through each result in json return
            for f in (file_detail):
                if self.threadPause() == False:
                    del fileList[:]
                    break

                istvshow = False
                f = self.runActions(RULES_ACTION_JSON, channel, f)
                durations = re.search('"duration" *: *([0-9]*?),', f)
                runtimes = re.search('"runtime" *: *([0-9]*?),', f)
                filetypes = re.search('"filetype" *: *"(.*?)",', f)
                labels = re.search('"label" *: *"(.*?)",', f)
                files = re.search('"file" *: *"(.*?)",', f)

                #if core variables have info proceed
                if filetypes and labels and files:
                    filetype = filetypes.group(1)
                    file = files.group(1)
                    label = self.CleanLabels(labels.group(1))

                    if label and label.lower() not in excludeLST:
                        if filetype == 'directory':
                            self.log('PluginWalk, directory')
                            # self.lastDirName = label
                            #try to speed up parsing by not over searching directories when media limit is low
                            if self.filecount < limit and self.dircount < dirlimit:

                                if file[0:4] != 'upnp':
                                    #if no return, try unquote
                                    if not self.PluginInfo(file):
                                        file = unquote(file).replace('",return)','')
                                        #remove unwanted reference from super.favourites
                                        try:
                                            file = (file.split('ActivateWindow(10025,"')[1])
                                        except:
                                            pass

                                if self.background == False:
                                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "Parsing " + (xName))

                                dirs.append(file+'@#@'+label)
                                self.dircount += 1
                                self.log('PluginWalk, dircount = ' + str(self.dircount) +'/'+ str(dirlimit))
                            else:
                                # reset dircount
                                self.dircount = 0
                                break

                        elif filetype == 'file':
                            self.log('PluginWalk, file')

                            if self.filecount < limit:
                                #Remove PlayMedia to keep link from launching
                                try:
                                    file = ((file.split('PlayMedia%28%22'))[1]).replace('%22%29','')
                                except:
                                    try:
                                        file = ((file.split('PlayMedia("'))[1]).replace('")','')
                                    except:
                                        pass

                                if file.startswith('plugin%3A%2F%2F'):
                                    file = unquote(file).replace('",return)','')

                                # If music duration returned, else 0
                                try:
                                    dur = int(durations.group(1))
                                except Exception,e:
                                    dur = 0

                                if dur == 0:
                                    try:
                                        dur = int(runtimes.group(1))
                                    except Exception,e:
                                        dur = 3600

                                    if not runtimes or dur == 0:
                                        dur = 3600

                                #correct UPNP default duration
                                if dur == 18000:
                                    dur = 3600

                                self.log('PluginWalk, dur = ' + str(dur))
                                
                                if dur > 0:
                                    self.filecount += 1
                                    self.log('PluginWalk, filecount = ' + str(self.filecount) +'/'+ str(limit))
                                    
                                    tmpstr = str(dur) + ','
                                    titles = re.search('"title" *: *"(.*?)",', f)
                                    showtitles = re.search('"showtitle" *: *"(.*?)",', f)
                                    plots = re.search('"plot" *: *"(.*?)",', f)
                                    plotoutlines = re.search('"plotoutline" *: *"(.*?)",', f)
                                    years = re.search('"year" *: *([\d.]*\d+)', f)
                                    genres = re.search('"genre" *: *\[(.*?)\],', f)
                                    playcounts = re.search('"playcount" *: *([\d.]*\d+),', f)
                                    imdbnumbers = re.search('"imdbnumber" *: *"(.*?)",', f)
                                    ratings = re.search('"mpaa" *: *"(.*?)",', f)
                                    descriptions = re.search('"description" *: *"(.*?)",', f)
                                    episodes = re.search('"episode" *: *([\d.]*\d+)', f)
                                    
                                    try:
                                        labelshowtitle = re.compile('(.+?) [(](\d{4})[)]$').findall(label)
                                        labeltitle = labelshowtitle[0][0]
                                        labelyear = int(labelshowtitle[0][1])
                                    except Exception,e:
                                        labeltitle = ''
                                        labelyear = ''
                                        pass
                                        
                                    try:  
                                        labelseasonepval = re.findall(r"(?:s|season)(\d{2})(?:e|x|episode|\n)(\d{2})", label, re.I)
                                        labelseasonval = int(labelseasonepval[0][0])
                                        labelepval = int(labelseasonepval[0][1])
                                    except Exception,e:
                                        labelseasonval = ''
                                        labelepval = ''
                                        pass

                                    #Traditional tvshow check
                                    if (episodes != None and episodes.group(1) != '-1') and showtitles != None and len(showtitles.group(1)) > 0:
                                        type = 'tvshow'
                                    #Modified tvshow check
                                    elif labelepval and not labeltitle:
                                        type = 'tvshow'
                                    else:
                                        type = 'movie'
                                        
                                    self.logDebug("PluginWalk, type = " + type) 
                                    
                                    if self.background == False:
                                        self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "adding %s Videos" % str(self.filecount))
                                        
                                    # if possible find year by title
                                    try:
                                        year = int(years.group(1))
                                    except:
                                        if labelyear:
                                            year = labelyear
                                        else:
                                            try:
                                                if type == 'tvshow':
                                                    year = int(((showtitles.group(1)).split(' ('))[1].replace(')',''))
                                                else:
                                                    year = int(((labels.group(1)).split(' ('))[1].replace(')',''))
                                            except Exception,e:
                                                year = 0
                                                pass

                                    if genres != None and len(genres.group(1)) > 0:
                                        genre = ((genres.group(1).split(',')[0]).replace('"',''))
                                    else:
                                        genre = 'Unknown'

                                    if playcounts != None and len(playcounts.group(1)) > 0:
                                        playcount = int(playcounts.group(1))
                                    else:
                                        playcount = 1
                                        
                                    self.logDebug("PluginWalk, playcount = " + str(playcount))

                                    if ratings != None and len(ratings.group(1)) > 0:
                                        rating = self.cleanRating(ratings.group(1))
                                        if type == 'movie':
                                            rating = rating[0:5]
                                            try:
                                                rating = rating.split(' ')[0]
                                            except:
                                                pass
                                    else:
                                        rating = 'NR'

                                    if imdbnumbers != None and len(imdbnumbers.group(1)) > 0:
                                        imdbnumber = imdbnumbers.group(1)
                                    else:
                                        imdbnumber = 0
                                    
                                    if plots != None and len(plots.group(1)) > 0:
                                        theplot = (plots.group(1)).replace('\\','').replace('\n','')
                                    elif plotoutlines != None and len(plotoutlines.group(1)) > 0:
                                        theplot = (plotoutlines.group(1)).replace('\\','').replace('\n','')
                                    elif descriptions != None and len(descriptions.group(1)) > 0:
                                        theplot = (descriptions.group(1)).replace('\\','').replace('\n','')
                                    else:
                                        theplot = (titles.group(1)).replace('\\','').replace('\n','')

                                    try:
                                        theplot = (self.trim(theplot, 350, '...'))
                                    except Exception,e:
                                        self.log("Plot Trim failed" + str(e))
                                        theplot = (theplot[:350])
                                    theplot = self.CleanLabels(theplot)

                                    # This is a TV show
                                    if type == 'tvshow':
                                        seasons = re.search('"season" *: *([0-9]*?),', f)
                                        episodes = re.search('"episode" *: *([0-9]*?),', f)
                                        swtitle = self.CleanLabels((labels.group(1)).replace('\\',''))
                                            
                                        try:
                                            seasonval = int(seasons.group(1))
                                            epval = int(episodes.group(1))
                                        except:
                                            if labelseasonval and labelepval:
                                                seasonval = labelseasonval
                                                epval = labelepval
                                            else:
                                                seasonval = -1
                                                epval = -1
                                            pass
             
                                        if seasonval > 0 and epval != -1:
                                            try:
                                                eptitles = swtitle.split(' - ')[1]
                                            except:
                                                try:
                                                    eptitles = swtitle.split('.')[1]
                                                except:
                                                    try:
                                                        eptitles = swtitle.split('. ')[1]
                                                    except:
                                                        eptitles = swtitle
                                                        pass
                                        else:
                                            try:
                                                SEinfo = (swtitle.split(' - ')[0]).lower()
                                                seasonval = SEinfo.split('e')[0].replace('s','')
                                                epval = SEinfo.split('e')[1]
                                                eptitles = (swtitle.split('- ', 1)[1])
                                                self.logDebug("PluginWalk, #S02E01 - eptitle")
                                            except:
                                                try:
                                                    SEinfo = (swtitle.split(' - ')[0]).lower()
                                                    seasonval = SEinfo.split('x')[0]
                                                    epval = SEinfo.split('x')[1]
                                                    eptitles = (swtitle.split('- ', 1)[1])
                                                    self.logDebug("PluginWalk, #2X01 - eptitle")
                                                except:
                                                    try:
                                                        SEinfo = (swtitle.split(' . ',1)[0]).lower()
                                                        seasonval = SEinfo.split('x')[0]
                                                        epval = SEinfo.split('x')[1]
                                                        eptitles = (swtitle.split(' . ', 1)[1])
                                                        self.logDebug("PluginWalk, #2X01 . eptitle")
                                                    except:
                                                        self.logDebug("PluginWalk, #seasonval, epval")
                                                        eptitles = swtitle
                                                        seasonval = -1
                                                        epval = -1
                                                        pass

                                        if seasonval > 0 and epval != -1:
                                            swtitle = (('0' if seasonval < 10 else '') + str(seasonval) + 'x' + ('0' if epval < 10 else '') + str(epval) + ' - ' + (eptitles)).replace('  ',' ')
                                        else:
                                            swtitle = swtitle.replace(' . ',' - ')

                                        showtitle = (showtitles.group(1))
                                        showtitle = self.CleanLabels(showtitle)

                                        if REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true' and PluginPath in DYNAMIC_PLUGIN_TV:
                                            year, imdbnumber, genre, rating, Managed, tagline = self.getEnhancedGuideData(showtitle, year, imdbnumber, genre, rating, type)
                                                
                                        GenreLiveID = [genre, type, imdbnumber, 0, Managed, playcount, rating]
                                        genre, LiveID = self.packGenreLiveID(GenreLiveID)
                                        swtitle = self.CleanLabels(swtitle)
                                        theplot = self.CleanLabels(theplot)
                                                                                    
                                        if not showtitle:
                                            showtitle = self.CleanLabels(foldername)
                                            
                                        tmpstr += showtitle + "//" + swtitle + "//" + theplot + "//" + genre + "////" + LiveID
                                        istvshow = True
                                    else:        
                                        album = re.search('"album" *: *"(.*?)"', f)
                                        # This is a movie
                                        if not album or len(album.group(1)) == 0:
                                        
                                            if labeltitle and labelyear:
                                                title = labeltitle
                                            elif len(titles.group(1)) > 0:
                                                title = titles.group(1)
                                            else:
                                                title = label
                                            
                                            #remove year from title if found
                                            if '(' in title:
                                                try:
                                                    if year == 0:
                                                        year = int(((title.split('('))[1]).replace(')',''))
                                                    title = ((title.split('('))[0])
                                                except:
                                                    pass
                                                
                                            taglines = re.search('"tagline" *: *"(.*?)",', f)                     
                                            if taglines and len(taglines.group(1)) > 0:
                                                tagline = (taglines.group(1)).replace('\\','')
                                            else:
                                                tagline = ''
                                                
                                            if REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true' and PluginPath in DYNAMIC_PLUGIN_MOVIE:
                                                year, imdbnumber, genre, rating, Managed, tagline = self.getEnhancedGuideData(title, year, imdbnumber, genre, rating, type, tagline)

                                            if not '(' in title and year != 0:
                                                showtitle = title + ' ('+str(year)+')'
                                            else:
                                                showtitle = title
                                                
                                            if not tagline:
                                                tagline = PluginName
                                                
                                            GenreLiveID = [genre, type, imdbnumber, 0, Managed, playcount, rating]
                                            genre, LiveID = self.packGenreLiveID(GenreLiveID)
                                            theplot = self.CleanLabels(theplot)
                                            
                                            if not showtitle:
                                                showtitle = self.CleanLabels(foldername)
                                            
                                            tmpstr += showtitle + "//" + tagline + "//" + theplot + "//" + genre + "////" + (LiveID)

                                        else: #Music
                                            tmpstr += label + "//"
                                            LiveID = 'music|0|0|False|1|NR|'
                                            artist = re.search('"artist" *: *"(.*?)"', f)
                                            
                                            if album != None and len(album.group(1)) > 0:
                                                albumTitle = album.group(1)
                                            else:
                                                albumTitle = label.group(1)
                                                
                                            if artist != None and len(artist.group(1)) > 0:
                                                artistTitle = album.group(1)
                                            else:
                                                artistTitle = ''
                                                
                                            albumTitle = self.CleanLabels(albumTitle)
                                            artistTitle = self.CleanLabels(artistTitle)
                                            tmpstr += albumTitle + "//" + artistTitle + "//" + 'Music' + "////" + LiveID
                                    
                                    file = self.CleanPlayableFile(file)
                                    tmpstr = tmpstr.replace("\\n", " ").replace("\\r", " ").replace("\\\"", "\"")
                                    tmpstr = tmpstr + '\n' + file.replace("\\\\", "\\")

                                    if self.channels[channel - 1].mode & MODE_ORDERAIRDATE > 0:
                                        seasoneplist.append([seasonval, epval, tmpstr])
                                    else:
                                        fileList.append(tmpstr)
                            # else:
                                # self.log('PluginWalk, filecount break/reset')
                                # self.filecount = 0
                                # break
                    else:
                        self.log('PluginWalk, ' + label.lower() + ' in excludeLST')
                        
            for item in dirs:
                self.log('PluginWalk, recursive directory walk')
                file, label = item.split('@#@')
                
                if self.filecount < limit:
                    #recursively scan all subfolders
                    fileList += self.PluginWalk(label, file, excludeLST, limit, xType, FleType)
        except Exception,e:
            self.log("PluginWalk, Failed " + str(e))
            pass
        
        fileList = sorted_nicely(fileList)
        if self.channels[channel - 1].mode & MODE_ORDERAIRDATE > 0:
            seasoneplist.sort(key=lambda seep: seep[1])
            seasoneplist.sort(key=lambda seep: seep[0])
            
            for seepitem in seasoneplist:
                fileList.append(seepitem[2])
                
        if self.filecount == 0:
            self.logDebug(json_folder_detail)
        self.log("PluginWalk return")
        
        # Stop playback from plugins
        if self.background == False:
            json_query = '{"jsonrpc":"2.0","method":"Input.ExecuteAction","params":{"action":"stop"},"id":1}'
            self.sendJSON(json_query);  
            
        return fileList
    

    # Run rules for a channel
    def runActions(self, action, channel, parameter):
        self.log("runActions " + str(action) + " on channel " + str(channel))
        if channel < 1:
            return

        self.runningActionChannel = channel
        index = 0

        for rule in self.channels[channel - 1].ruleList:
            if rule.actions & action > 0:
                self.runningActionId = index

                if self.background == False:
                    self.updateDialog.update(self.updateDialogProgress, "Updating channel " + str(self.settingChannel), "processing rule " + str(index + 1))

                parameter = rule.runAction(action, self, parameter)
            index += 1
        
        self.runningActionChannel = 0
        self.runningActionId = 0
        return parameter


    def threadPause(self):
        if threading.activeCount() > 1:
            while self.threadPaused == True and self.myOverlay.isExiting == False:
                time.sleep(self.sleepTime)
            # This will fail when using config.py
            try:
                if self.myOverlay.isExiting == True:
                    self.log("IsExiting")
                    return False
            except Exception,e:
                pass
        return True


    def escapeDirJSON(self, dir_name):
        mydir = uni(dir_name)
        if (mydir.find(":")):
            mydir = mydir.replace("\\", "\\\\")
        return mydir


    def getSmartPlaylistType(self, dom):
        self.log('getSmartPlaylistType')

        try:
            pltype = dom.getElementsByTagName('smartplaylist')
            return pltype[0].attributes['type'].value
        except Exception,e:
            self.log("Unable to get the playlist type.", xbmc.LOGERROR)
            return ''

    
    def readXMLTV(self, filename):
        xbmc.log("readXMLTV")
        if Primary_Cache_Enabled == True:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = quarterly.cacheFunction(self.readXMLTV_NEW, filename)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.readXMLTV_NEW(filename)
                pass
        else:
            result = self.readXMLTV_NEW(filename)
        if not result:
            result = ['XMLTV ERROR : IMPROPER FORMATING']
        return result   
     
     
    def readXMLTV_NEW(self, filename):
        self.log('readXMLTV_NEW')
        if len(self.cached_readXMLTV) == 0:
            try:
                if filename[0:4] == 'http':
                    self.log("findZap2itID, filename http = " + filename)
                    f = open_url(filename)
                else:
                    self.log("findZap2itID, filename local = " + filename)
                    f = open(filename, "r")
                context = ET.iterparse(f, events=("start", "end"))
                context = iter(context)
                event, root = context.next()
                for event, elem in context:
                    if event == "end":
                        if elem.tag == "channel":
                            CHid = ascii(elem.get("id"))
                            for title in elem.findall('display-name'):
                                channel = ascii(title.text.replace('<display-name>','').replace('</display-name>','').replace('-DT','DT').replace(' DT','DT').replace('DT','').replace('-HD','HD').replace(' HD','HD').replace('HD','').replace('-SD','SD').replace(' SD','SD').replace('SD','').replace("'",'').replace(')',''))
                                channel = channel+' : '+CHid
                                self.cached_readXMLTV.append(channel)
                f.close()
                return self.cached_readXMLTV
            except Exception,e:
                self.log("readXMLTV, Failed! " + str(e))
                self.cached_readXMLTV = []
                channels = ['XMLTV ERROR : IMPROPER FORMATING']
                return channels
                    
 
    def findZap2itID(self, CHname, filename):
        if len(CHname) <= 1:
            CHname = 'Unknown'
        self.log("findZap2itID, CHname = " + CHname)
        show_busy_dialog()
        orgCHname = CHname
        CHname = CHname.upper()
        XMLTVMatchlst = []
        sorted_XMLTVMatchlst = []
        found = False
        try:
            if filename == 'pvr':
                self.log("findZap2itID, pvr backend")             
                if not self.cached_json_detailed_xmltvChannels_pvr:
                    self.log("findZap2itID, no cached_json_detailed_xmltvChannels")
                    json_query = uni('{"jsonrpc":"2.0","method":"PVR.GetChannels","params":{"channelgroupid":2,"properties":["thumbnail"]},"id": 1 }')
                    json_detail = self.sendJSON(json_query)
                    self.cached_json_detailed_xmltvChannels_pvr = re.compile( "{(.*?)}", re.DOTALL ).findall(json_detail)
                file_detail = self.cached_json_detailed_xmltvChannels_pvr
                
                for f in file_detail:
                    CHids = re.search('"channelid" *: *(.*?),', f)
                    dnames = re.search('"label" *: *"(.*?)"', f)
                    thumbs = re.search('"thumbnail" *: *"(.*?)"', f)
                   
                    if CHids and dnames:
                        CHid = CHids.group(1)
                        dname = dnames.group(1)       
                        CHname = CHname.replace('-DT','DT').replace(' DT','DT').replace('DT','').replace('-HD','HD').replace(' HD','HD').replace('HD','').replace('-SD','SD').replace(' SD','SD').replace('SD','')
                        matchLST = [CHname, 'W'+CHname, CHname+'HD', CHname+'DT', str(CHid)+' '+CHname, orgCHname.upper(), 'W'+orgCHname.upper(), orgCHname.upper()+'HD', orgCHname.upper()+'DT', str(CHid)+' '+orgCHname.upper(), orgCHname]
                        dnameID = dname + ' : ' + CHid
                        self.logDebug("findZap2itID, dnameID = " + dnameID)
                        XMLTVMatchlst.append(dnameID)
            else:
                XMLTVMatchlst = self.readXMLTV(filename)
                try:
                    CHnum = int(CHname.split(' ')[0])
                    CHname = (CHname.split(' ')[1]).upper()
                except:
                    CHnum = 0
                    pass
                
                CHname = CHname.replace('-DT','DT').replace(' DT','DT').replace('DT','').replace('-HD','HD').replace(' HD','HD').replace('HD','').replace('-SD','SD').replace(' SD','SD').replace('SD','')
                matchLST = [CHname, 'W'+CHname, CHname+'HD', CHname+'DT', str(CHnum)+' '+CHname, orgCHname.upper(), 'W'+orgCHname.upper(), orgCHname.upper()+'HD', orgCHname.upper()+'DT', str(CHnum)+' '+orgCHname.upper(), orgCHname]
                self.logDebug("findZap2itID, Cleaned CHname = " + CHname)
                
            sorted_XMLTVMatchlst = sorted_nicely(XMLTVMatchlst)
            for n in range(len(sorted_XMLTVMatchlst)):
                try:
                    CHid = '0'
                    found = False
                    dnameID = sorted_XMLTVMatchlst[n]
                    dname = dnameID.split(' : ')[0]
                    CHid = dnameID.split(' : ')[1]

                    if dname.upper() in matchLST: 
                        found = True
                        hide_busy_dialog()
                        return orgCHname, CHid
                except:
                    hide_busy_dialog()
                    pass
                    
            if not found:
                hide_busy_dialog()
                XMLTVMatchlst = []

                for s in range(len(sorted_XMLTVMatchlst)):
                    try:
                        dnameID = sorted_XMLTVMatchlst[s]
                        dname = dnameID.split(' : ')[0]
                        CHid = dnameID.split(' : ')[1]
                                        
                        try:
                            CHid = CHid.split(', icon')[0]
                        except:
                            pass
                            
                        line = dname + ' : ' + CHid 
                        if dname[0:3] != 'en': 
                            XMLTVMatchlst.append(line)
                    except:
                        hide_busy_dialog()
                        pass
                        
                if XMLTVMatchlst:
                    select = selectDialog(XMLTVMatchlst, 'Select matching id to [B]%s[/B]' % orgCHname, 30000)
                    dnameID = XMLTVMatchlst[select]
                    CHid = dnameID.split(' : ')[1]
                    dnameID = dnameID.split(' : ')[0]
                    return dnameID, CHid
                    
        except Exception,e:
            hide_busy_dialog()
            self.log("findZap2itID, Failed! " + str(e))
            
            
    def IPTVtuning(self, type, url, Random=False):
        self.log('IPTVtuning')
        SortIPTVList = []
        TMPIPTVList = []
        IPTVNameList = []
        IPTVPathList = []
        show_busy_dialog()
        try:
            if type == 'IPTV':
                TMPIPTVList = IPTVtuning(url)
            elif type == 'LS':
                TMPIPTVList = LSTVtuning(url)
            elif type == 'Navix':
                TMPIPTVList = NaviXtuning(url)
            
            if len(TMPIPTVList) == 0:
                SortIPTVList = ['This list is empty or unavailable@#@ ']
            elif Random == True:
                SortIPTVList = TMPIPTVList
                random.shuffle(SortIPTVList)
            else:
                SortIPTVList = sorted_nicely(TMPIPTVList)

            for n in range(len(SortIPTVList)):
                if SortIPTVList[n] != None:
                    IPTVNameList.append((SortIPTVList[n]).split('@#@')[0])   
                    IPTVPathList.append((SortIPTVList[n]).split('@#@')[1])
        except Exception,e:
            self.log("IPTVtuning, Failed! " + str(e))    
        hide_busy_dialog()
        return IPTVNameList, IPTVPathList

        
    def fillPluginList(self):
        self.log('fillPluginList')
        json_query = uni('{"jsonrpc":"2.0","method":"Addons.GetAddons","params":{"type":"xbmc.addon.video","content":"video","enabled":true,"properties":["path","name"]}, "id": 1 }')
        json_detail = self.sendJSON(json_query)
        detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_detail)
        TMPpluginList = []
        try:
            for f in detail:
                names = re.search('"name" *: *"(.*?)",', f)
                paths = re.search('"addonid" *: *"(.*?)",', f)
                if names and paths:
                    name = self.CleanLabels(names.group(1))
                    path = paths.group(1)
                    if name.lower() != 'super favourites' and name.lower() != '.playon browser' and name.lower() != 'playon browser':
                        TMPpluginList.append(name+','+path)  
                    
            SortedpluginList = sorted_nicely(TMPpluginList)
            for i in range(len(SortedpluginList)):
                self.pluginNameList.append((SortedpluginList[i]).split(',')[0])
                self.pluginPathList.append((SortedpluginList[i]).split(',')[1]) 
        except Exception,e:
            self.log("fillPluginList, Failed! " + str(e))

        if len(TMPpluginList) == 0:
            self.pluginNameList = ['No Kodi plugins unavailable!']
    
    
    def fillPVR(self):
        self.log('fillPVR')
        show_busy_dialog()
        json_query = uni('{"jsonrpc":"2.0","method":"PVR.GetChannels","params":{"channelgroupid":2,"properties":["thumbnail"]},"id": 1 }')
        json_detail = self.sendJSON(json_query)
        file_detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_detail)
        TMPPVRList = []
        PVRNameList = []
        PVRPathList = []
        self.cached_json_detailed_xmltvChannels_pvr = [] 
        
        #PVR Path by XBMC Version
        if self.XBMCversion() < 14:
            PVRverPath = "pvr://channels/tv/All TV channels/"
        else:
            PVRverPath = "pvr://channels/tv/All channels/"          
        try:         
            for f in file_detail:
                CHid = 0
                CHname = ''
                thumb = ''
                CHids = re.search('"channelid" *: *(.*?),', f)
                CHnames = re.search('"label" *: *"(.*?)"', f)
                thumbs = re.search('"thumbnail" *: *"(.*?)"', f)
                
                if CHids and CHnames:
                    CHid = int(CHids.group(1))
                    CHname = CHnames.group(1)
                    
                    #Download icon to channel logo folder
                    if thumbs and REAL_SETTINGS.getSetting('EnhancedGuideData') == 'true':
                        thumb = thumbs.group(1)
                        GrabLogo(thumb, CHname + ' PVR')
                                               
                    name = '[COLOR=blue][B]'+str(CHid)+'[/B][/COLOR] - ' + CHname
                    path = PVRverPath + str(CHid - 1) + ".pvr"
                    TMPPVRList.append(name+'@#@'+path)  

            SortedPVRList = sorted_nicely(TMPPVRList)
            for i in range(len(SortedPVRList)):  
                PVRNameList.append((SortedPVRList[i]).split('@#@')[0])  
                PVRPathList.append((SortedPVRList[i]).split('@#@')[1])          
        except Exception,e:
            self.log("fillPVR, Failed! " + str(e))

        if len(TMPPVRList) == 0:
            PVRNameList = ['Kodi PVR is empty or unavailable!']
        hide_busy_dialog() 
        return PVRNameList, PVRPathList

        
    def fillFavourites(self):
        self.log('fillFavourites')
        show_busy_dialog()
        json_query = uni('{"jsonrpc":"2.0","method":"Favourites.GetFavourites","params":{"properties": ["path", "thumbnail", "window", "windowparameter"]},"id":3}')
        json_detail = self.sendJSON(json_query)
        detail = re.compile( "{(.*?)}", re.DOTALL ).findall(json_detail)
        TMPfavouritesList = []
        FavouritesNameList = []
        FavouritesPathList = []
        try:
            for f in detail:
                paths = re.search('"path" *: *"(.*?)",', f)
                names = re.search('"title" *: *"(.*?)",', f)
                types = re.search('"type" *: *"(.*?)"', f)
                if types != None and len(types.group(1)) > 0:
                    type = types.group(1)
                    if names and paths:
                        name = self.CleanLabels(names.group(1))
                        if type == 'media':
                            path = "PlayMedia(%s)" % (paths.group(1))
                        elif type == 'script': 
                            path = "RunScript(%s)" % (paths.group(1)) 
                        # elif "window" in fav and "windowparameter" in fav:
                            # path = "ActivateWindow(%s,%s)" % (fav["window"], fav["windowparameter"])
                            TMPfavouritesList.append(name+'@#@'+path) 
            SortedFavouritesList = sorted_nicely(TMPfavouritesList)
            for i in range(len(SortedFavouritesList)):  
                FavouritesNameList.append((SortedFavouritesList[i]).split('@#@')[0])  
                FavouritesPathList.append((SortedFavouritesList[i]).split('@#@')[1])          
        except Exception,e:
            self.log("fillFavourites, Failed! " + str(e))

        if len(TMPfavouritesList) == 0:
            FavouritesNameList = ['Kodi Favorites is empty or unavailable!']
        hide_busy_dialog() 
        return FavouritesNameList, FavouritesPathList
        
        
    def fillExternalList(self, type, source='', list='Community', Random=False):
        self.log('fillExternalList, type = ' + type)
        show_busy_dialog()
        TMPExternalList = []
        ExternalNameList = []
        SortedExternalList = []
        ExternalSetting1List = []
        ExternalSetting2List = []
        ExternalSetting3List = []
        ExternalSetting4List = []
        RSSURL = 'http://raw.github.com/Lunatixz/PseudoTV_Lists/master/rss.xml'
        YoutubeChannelURL = 'http://raw.github.com/Lunatixz/PseudoTV_Lists/master/youtube_channels.xml'
        YoutubePlaylistURL = 'http://raw.github.com/Lunatixz/PseudoTV_Lists/master/youtube_playlists.xml'
        YoutubeChannelNetworkURL = 'http://raw.github.com/Lunatixz/PseudoTV_Lists/master/youtube_channels_networks.xml'
        YoutubePlaylistNetworkURL = 'http://raw.github.com/Lunatixz/PseudoTV_Lists/master/youtube_playlists_networks.xml'

        if list == 'Donor':
            PluginURL = BASEURL + 'addons.ini'
            InternetURL = BASEURL + 'internettv.ini'
            LiveURL = BASEURL + 'livetv.ini'
            ExternalPlaylistURL = BASEURL + 'InternetTV_Playlists.ini'
               
        if type == 'LiveTV':
            url = LiveURL
        elif type == 'InternetTV':
            url = InternetURL
        elif type == 'YouTube':
            if source == 'Channel':
                url = YoutubeChannelURL
                id = '1'
            elif source == 'Playlist':
                url = YoutubePlaylistURL
                id = '2'
            elif source == 'Multi Playlist':
                url = YoutubePlaylistNetworkURL
                id = '7'
            elif source == 'Multi Channel': 
                url = YoutubeChannelNetworkURL
                id = '8'
        elif type == 'RSS':
            url = RSSURL
            id = '1'
        elif type == 'Plugin':
            url = PluginURL
        elif type == 'ExternalPlaylist':
            url = ExternalPlaylistURL
        try:
            if list == 'Donor':
                data = open_url_up_cached(url, UPASS)
            else:
                data = readline_url(url)
            data = ([x for x in data if x != '']) #remove empty lines
            
            for i in range(len(data)):
                Pluginvalid = False
                line = str(data[i]).replace("\n","").replace('""',"")

                if type == 'RSS' or source == 'Channel' or source == 'Playlist':
                    line = line.split(",")
                else:
                    line = line.split("|")

                if len(line) == 7:
                    if not str(line).startswith(';'):
                        genre = uni((line[0]).title())
                        chtype = uni(line[1])
                        setting_1 = uni(line[2])
                        setting_2 = uni(line[3])
                        setting_3 = uni(line[4])
                        setting_4 = uni(line[5])
                        channel_name = uni((self.CleanLabels(line[6])).title())
                        
                        if genre.lower() == 'tv':
                            genre = '[COLOR=yellow]'+genre+'[/COLOR]'
                        elif genre.lower() == 'movies':
                            genre = '[COLOR=cyan]'+genre+'[/COLOR]'
                        elif genre.lower() == 'episodes':
                            genre = '[COLOR=yellow]'+genre+'[/COLOR]'
                        elif genre.lower() == 'sports':
                            genre = '[COLOR=red]'+genre+'[/COLOR]'
                        elif genre.lower() == 'news':
                            genre = '[COLOR=green]'+genre+'[/COLOR]'
                        elif genre.lower() == 'kids':
                            genre = '[COLOR=orange]'+genre+'[/COLOR]'
                        elif genre.lower() == 'music':
                            genre = '[COLOR=purple]'+genre+'[/COLOR]'
                        elif genre.lower() == 'other':
                            genre = '[COLOR=grey]'+genre+'[/COLOR]'
                        
                        if chtype == '15':
                            Pluginvalid = self.plugin_ok(setting_1)
                            channel_name = (((setting_1.split('//')[1]).split('/')[0]).replace('plugin.video.','').replace('plugin.audio.','')).title() + ': ' + genre + ' - ' + channel_name
                        elif chtype == '16':
                            Pluginvalid = self.playon_player()
                            channel_name = (((setting_1.split('//')[1]).split('/')[0]).title()) + ': ' + genre + ' - ' + channel_name
                        elif chtype == '9':
                            Pluginvalid = self.Valid_ok(setting_2)
                            channel_name = channel_name + ' - ' + genre
                        elif chtype == '8':
                            Pluginvalid = self.Valid_ok(setting_2)
                                                    
                            if setting_2[0:9].lower() != 'plugin://':
                                setting_2 = 'plugin://' + setting_2
                        
                            if setting_2.startswith('plugin://'):    
                                channel_name = (((setting_2.split('//')[1]).split('/')[0]).replace('plugin.video.','').replace('plugin.audio.','')).title() + ' - ' + channel_name
                            else:
                                channel_name =  'Internet - ' + channel_name
                            
                        elif chtype == '10':
                            Pluginvalid = self.youtube_player()
                            channel_name = ((channel_name.title()) + ' - ' + genre)

                        if Pluginvalid != False:
                            if chtype == '10' and len(setting_2) == 0:
                                setting_2 = id
                            TMPExternalList.append(channel_name+'@#@'+setting_1+'@#@'+setting_2+'@#@'+setting_3+'@#@'+setting_4)

                elif len(line) == 2:
                    if not str(line).startswith(';'):
                        setting_1 = line[0]
                        channel_name = line[1]
                        if setting_1.startswith('http'):
                            Pluginvalid = self.Valid_ok(setting_1)
                            if Pluginvalid != False:
                                TMPExternalList.append(channel_name+'@#@'+setting_1+'@#@'+id+'@#@'+'25'+'@#@'+'Default')
                        else:
                            if self.youtube_player() != False:
                                TMPExternalList.append(channel_name+'@#@'+setting_1+'@#@'+id+'@#@'+'25'+'@#@'+'Default')
                
                elif len(line) == 3:
                    if not str(line).startswith(';'):
                        type = line[0]
                        url = line[1]
                        channel_name = line[2]
                        if type.lower() == source.lower():
                            if url.startswith('http'):
                                Pluginvalid = self.Valid_ok(url)
                                if Pluginvalid != False:
                                    # append as string element for easier sorting? no need for indexes
                                    TMPExternalList.append(channel_name+'@#@'+url+'@#@'+''+'@#@'+''+'@#@'+'')
                                    
            if Random == True:
                SortedExternalList = TMPExternalList
                random.shuffle(SortedExternalList)
            else:
                SortedExternalList = sorted_nicely(TMPExternalList)
                
            for n in range(len(SortedExternalList)):
                if SortedExternalList[n] != None:
                    ExternalNameList.append((SortedExternalList[n]).split('@#@')[0])   
                    ExternalSetting1List.append((SortedExternalList[n]).split('@#@')[1])
                    ExternalSetting2List.append((SortedExternalList[n]).split('@#@')[2])
                    ExternalSetting3List.append((SortedExternalList[n]).split('@#@')[3])
                    ExternalSetting4List.append((SortedExternalList[n]).split('@#@')[4])
        except Exception,e:
            self.log("fillExternalList, Failed! " + str(e))

        if len(TMPExternalList) == 0:
            ExternalNameList = ['This list is empty or unavailable, Please try again later.']
        hide_busy_dialog() 
        return ExternalNameList, ExternalSetting1List, ExternalSetting2List, ExternalSetting3List, ExternalSetting4List
              
        
    def fillHDHR(self,favorite=False):
        self.log("fillHDHR")
        show_busy_dialog()
        Chanlist = []
        Favlist = []
        HDHRNameList = ['']
        HDHRPathList  = ['']
        list = ''
        try:
            devices = hdhr.discover()
            for i in range(len(devices)):
                url = (str(devices[i]).split(':url=')[1]).replace('>','')
                try:
                    list = list + urlopen(url).read()
                except:
                    pass
            file_detail = re.compile( "{(.*?)}", re.DOTALL ).findall(list)
            
            for f in file_detail:
                match = ''
                link = ''
                chnum = 0
                fav = False
                drm = False
                tmp = ''
                match = re.search('"GuideName" *: *"(.*?)",', f)    
                if match != None and len(match.group(1)) > 0:
                    chname = match.group(1)
                    links = re.search('"URL" *: *"(.*?)"', f)
                    chnums = re.search('"GuideNumber" *: *"([\d.]*\d+)"', f)
                    favs = re.search('"Favorite" *: *([\d.]*\d+)', f)
                    drms = re.search('"DRM" *: *([\d.]*\d+)', f)

                    if links != None and len(links.group(1)) > 0:
                        link = links.group(1)

                    if chnums != None and len(chnums.group(1)) > 0:
                        chnum = chnums.group(1)

                    if favs != None and len(favs.group(1)) > 0:
                        fav = bool(favs.group(1))
                        
                    if drms != None and len(drms.group(1)) > 0:
                        drm = bool(drms.group(1))

                    if fav:
                        chname = chname+'[COLOR=gold] [Favorite][/COLOR]'
                    if drm:
                        chname = chname+'[COLOR=red] [DRM][/COLOR]'
                                           
                    chname = '[COLOR=blue][B]'+chnum+'[/B][/COLOR] - ' + chname
                    tmp = chname + '@#@' + link
                    
                    if favorite:
                        if favs:
                            Chanlist.append(tmp)
                    else:
                        Chanlist.append(tmp)
            SortChanlist = sorted_nicely(Chanlist)
            
            for n in range(len(SortChanlist)):
                if SortChanlist[n] != None:
                    HDHRNameList.append((SortChanlist[n]).split('@#@')[0])   
                    HDHRPathList.append((SortChanlist[n]).split('@#@')[1])
        except Exception,e:
            self.log("fillHDHR, Failed! " + str(e))

        if len(Chanlist) == 0:
            HDHRNameList = ['HDHR ERROR: Unable to find device or favorite channels']
        hide_busy_dialog()
        return removeStringElem(HDHRNameList), removeStringElem(HDHRPathList)

        
    def sbManaged(self, tvdbid):
        self.log("sbManaged")
        sbManaged = False
        if REAL_SETTINGS.getSetting('sickbeard.enabled') == "true":
            try:
                sbManaged = self.sbAPI.isShowManaged(tvdbid)
            except Exception,e:
                self.log("sbManaged, Failed! " + str(e))
        return sbManaged


    def cpManaged(self, title, imdbid):
        self.log("cpManaged")
        cpManaged = False
        if REAL_SETTINGS.getSetting('couchpotato.enabled') == "true":
            try:
                r = str(self.cpAPI.getMoviebyTitle(title))
                r = r.split("u'")
                match = [s for s in r if imdbid in s][1]
                if imdbid in match:
                    cpManaged = True
            except Exception,e:
                self.log("cpManaged, Failed! " + str(e))
        return cpManaged
        
        
    def getYear(self, type, title):
        self.log("getYear")
        try:
            self.metaget = metahandlers.MetaData(preparezip=False)
            year = self.metaget.get_meta(type, title)['year']
            if not year:
                year = 0
        except Exception,e:
            year = 0
            self.log("getYear, Failed! " + str(e))
        return year
        
        
    def getTVDBID(self, title, year):
        self.log("getTVDBID")
        title = ConStr(title)
        try:
            self.metaget = metahandlers.MetaData(preparezip=False)
            tvdbid = self.metaget.get_meta('tvshow', title, year=year)['tvdb_id']
            if not tvdbid:
                tvdbid = 0
        except Exception,e:
            tvdbid = 0
            self.log("getTVDBID, Failed! " + str(e))
        return tvdbid
         
         
    def getIMDBIDmovie(self, title, year=''):
        self.log("getIMDBIDmovie")
        title = ConStr(title)
        try:
            self.metaget = metahandlers.MetaData(preparezip=False)
            imdbid = (self.metaget.get_meta('movie', title, year=year)['imdb_id'])
            if not imdbid:
                imdbid = 0
        except Exception,e:
            imdbid = 0
            self.log("getIMDBIDmovie, Failed! " + str(e))
        return imdbid

        
    def getGenre(self, type, title, year=''):
        self.log("getGenre")
        title = ConStr(title)
        try:
            self.metaget = metahandlers.MetaData(preparezip=False)
            genre = self.metaget.get_meta(type, title, year=year)['genre']
            try:
                genre = str(genre.split(',')[0])
            except:
                pass
            try:
                genre = str(genre.split(' / ')[0])
            except:
                pass
            if not genre:
                genre = 'Unknown'
        except Exception,e:
            genre = 'Unknown'      
            self.log("getGenre, Failed! " + str(e))
        return genre
        

    def getRating(self, type, title, year=''):
        self.log("getRating")
        title = ConStr(title)
        try:   
            self.metaget = metahandlers.MetaData(preparezip=False)
            rating = self.metaget.get_meta(type, title, year=year)['mpaa']
            if not rating:
                rating = 'NR'
        except Exception,e:
            rating = 'NR'
            self.log("getRating, Failed! " + str(e))
        rating = (self.cleanRating(rating))
        return rating
        

    def getTagline(self, title, year=''):
        self.log("getTagline")
        title = ConStr(title)
        try:
            self.metaget = metahandlers.MetaData(preparezip=False)
            tagline = self.metaget.get_meta('movie', title, year=year)['tagline']
            if not tagline:
                tagline = ''
        except Exception,e:
            tagline = ''
            self.log("getTagline, Failed! " + str(e))
        return tagline
                

    def getIMDBIDtv(self, title, year):
        self.log("getIMDBIDtv")
        title = ConStr(title)
        try:
            self.metaget = metahandlers.MetaData(preparezip=False)
            imdbid = self.metaget.get_meta('tvshow', title, year=year)['imdb_id']
            if not imdbid:
                imdbid = 0
        except Exception,e:
            imdbid = 0
            self.log("getIMDBIDtv, Failed! " + str(e))
        return imdbid
        
        
    def getTVDBIDbyZap2it(self, dd_progid):
        xbmc.log("getTVDBIDbyZap2it")
        if Primary_Cache_Enabled == True:
            try:
                setProperty("PTVL.CHKCache", "false")
                result = parsers.cacheFunction(self.getTVDBIDbyZap2it_NEW, dd_progid)
                setProperty("PTVL.CHKCache", "true")
            except:
                result = self.getTVDBIDbyZap2it_NEW(dd_progid)
                pass
        else:
            result = self.getTVDBIDbyZap2it_NEW(dd_progid)
        if not result:
            result = 0
        return result  
    

    def getTVDBIDbyZap2it_NEW(self, dd_progid):
        self.log("getTVDBIDbyZap2it cache")
        try:
            tvdbid = self.tvdbAPI.getIdByZap2it(dd_progid)
            if not tvdbid or tvdbid == 'Empty':
                tvdbid = 0
        except Exception,e:
            tvdbid = 0
            self.log("getTVDBIDbyZap2it, Failed! " + str(e))
        return tvdbid
        
        
    def getTVINFObySubtitle(self, title, subtitle):
        self.log("getTVINFObySubtitle")
        title = ConStr(title)
        try:
            episode = self.t[title].search(subtitle, key = 'episodename')
            # Output example: [<Episode 01x01 - My First Day>]
            episode = str(episode[0])
            episode = episode.split('x')
            seasonNumber = int(episode[0].split('Episode ')[1])
            episodeNumber = int(episode[1].split(' -')[0])
            episodeName = str(episode[1]).split('- ')[1].replace('>','')
            if not episodeName or episodeName == 'Empty':
                episodeName = ''
            if not seasonNumber or seasonNumber == 'Empty':
                seasonNumber = 0    
            if not episodeNumber or episodeNumber == 'Empty':
                episodeNumber = 0
        except Exception,e:
            episodeName = ''
            seasonNumber = 0
            episodeNumber = 0
            self.log("getTVINFObySubtitle, Failed! " + str(e))
        return episodeName, seasonNumber, episodeNumber

        
    def getTVINFObySE(self, title, seasonNumber, episodeNumber):
        self.log("getTVINFObySE")
        title = ConStr(title)
        try:
            episode = self.t[title][seasonNumber][episodeNumber]
            episodeName = str(episode['episodename'])
            episodeDesc = str(episode['overview'])
            episodeGenre = str(self.t[title]['genre'])
            # Output ex. Comedy|Talk Show|
            episodeGenre = str(episodeGenre)
            try:
                episodeGenre = str(episodeGenre.split('|')[1])
            except:
                pass
        except Exception,e:
            episodeName = ''
            episodeDesc = ''
            episodeGenre = 'Unknown'
            self.log("getTVINFObySE, Failed! " + str(e))
        return episodeName, episodeDesc, episodeGenre
        
        
    def getEnhancedGuideData(self, showtitles, year, imdbnumber, genre, rating, type, tagline=None):
        self.log('getEnhancedGuideData_Cache')
        if Primary_Cache_Enabled == True:
            try:
                result = parsersGD.cacheFunction(self.getEnhancedGuideData_NEW, showtitles, year, imdbnumber, genre, rating, type, tagline)
            except:
                result = self.getEnhancedGuideData_NEW(showtitles, year, imdbnumber, genre, rating, type, tagline)
                pass
        else:
            result = self.getEnhancedGuideData_NEW(showtitles, year, imdbnumber, genre, rating, type, tagline)
        if not result:
            result = []
        return result  
        
        
    def getEnhancedGuideData_NEW(self, showtitles, year, imdbnumber, genre, rating, type, tagline=None):
        self.logDebug("getEnhancedGuideData")
        Managed = False
        if type == 'movie':
            if year == 0:
                year = self.getYear(type, showtitles)
                
            if imdbnumber == 0:
                imdbnumber = self.getIMDBIDmovie(showtitles, year)
                                            
            if genre == 'Unknown':
                genre = self.getGenre(type, showtitles, year)

            if rating == 'NR':
                rating = self.getRating(type, showtitles, year)
            
            if imdbnumber != 0:
                Managed = self.cpManaged(showtitles, imdbnumber)   
                        
            if not tagline:
                tagline = self.getTagline(showtitles, year)
        else:
            if year == 0:
                year = self.getYear(type, showtitles)
                
            if imdbnumber == 0:
                imdbnumber = self.getTVDBID(showtitles, year)                         

            if genre == 'Unknown':
                genre = self.getGenre(type, showtitles, year)
                
            if rating == 'NR':
                rating = self.getRating(type, showtitles, year)

            if imdbnumber != 0:
                Managed = self.sbManaged(imdbnumber)
        
        return year, imdbnumber, genre, rating, Managed, tagline
        
        
    def getOSPpath(self, OSplat):
        self.log("getOSPpath") 
        if OSplat == '0':
            return 'androidarm/rtmpdump'
        elif OSplat == '1':
            return 'android86/rtmpdump'
        elif OSplat == '2':
            return 'atv1linux/rtmpdump'
        elif OSplat == '3':
            return 'atv1stock/rtmpdump'
        elif OSplat == '4':
            return 'atv2/rtmpdump'
        elif OSplat == '5':
            return 'ios/rtmpdump'
        elif OSplat == '6':
            return 'linux32/rtmpdump'
        elif OSplat == '7':
            return 'linux64/rtmpdump'
        elif OSplat == '8':
            return 'mac32/rtmpdump'
        elif OSplat == '9':
            return 'mac64/rtmpdump'
        elif OSplat == '10':
            return 'pi/rtmpdump'
        elif OSplat == '11':
            return 'win/rtmpdump.exe'
        elif OSplat == '12':
            return '/usr/bin/rtmpdump'
            
            
    def getFileListCache(self, chtype, channel, purge=False):
        self.log("getFileListCache")
        #Cache name
        cachetype = str(chtype) + ':' + str(channel)
        
        #Set Life of cache
        if chtype <= 7:
            life = SETTOP_REFRESH - 1000
        elif chtype == 8:
            life = 72
        else:
            life = 24
            
        self.FileListCache = StorageServer.StorageServer(("plugin://script.pseudotv.live/%s" % cachetype),life)
        if purge:
            self.FileListCache.delete("%")

         
    def clearFileListCache(self, chtype=-1, channel=9999):
        self.log("clearFileListCache")
        if channel == 9999:
            for n in range(999):
                for i in range(15):
                    try:
                        self.getFileListCache(i+1, n+1, True)
                    except:
                        pass
            return True
        else:
            self.getFileListCache(chtype, channel, True)
            return True