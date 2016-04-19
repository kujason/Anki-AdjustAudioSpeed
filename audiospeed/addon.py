import re
import time
import os, subprocess
import anki.sound

import sys

from threading import Thread
from Queue import Queue, Empty

from Queue import Queue

from anki.sound import play
from anki.sound import mplayerQueue, mplayerClear, mplayerEvt
from anki.sound import MplayerMonitor

from anki.hooks import addHook, wrap
from aqt.reviewer import Reviewer
from aqt.utils import showInfo

sound_regex = ur"\[sound:(.*?)\]"

audio_file = ""
audio_speed = 1.0
audio_replay = False

stdoutQueue = Queue()

# Debugging Messages
#messageBuff = ""

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()

def my_keyHandler(self, evt):
    #global messageBuff
    global audio_speed, audio_replay
    
    key = unicode(evt.text())

    if key == "0":
        audio_speed = 1.0
    elif key == "[":
        audio_speed = max(0.1, audio_speed - 0.1)
    elif key == "]":
        audio_speed = min(4.0, audio_speed + 0.1)
    
    if key in "0[]":    
        if audio_replay:
            play(audio_file)
        elif anki.sound.mplayerManager is not None:
            if anki.sound.mplayerManager.mplayer is not None: 
                anki.sound.mplayerManager.mplayer.stdin.write("af_add scaletempo=stride=10:overlap=0.8\n")
                anki.sound.mplayerManager.mplayer.stdin.write(("speed_set %f \n" % audio_speed))
    
    if key == "p":
        anki.sound.mplayerManager.mplayer.stdin.write("pause\n")
    elif key == "l":
        audio_replay = not audio_replay
        if audio_replay:
            showInfo("Auto Replay ON")
        else:
            showInfo("Auto Replay OFF")
    
    if key == "r":
        anki.sound.mplayerClear = True

    # Clear Message Buffer (for debugging)
    #if key == "8":
    #    messageBuff = ""
    
    # Show Message Buffer (for debugging)
    #if key == "9":
    #    sys.stderr.write(messageBuff)
            
def my_runHandler(self):
    #global messageBuff
    global currentlyPlaying
    
    self.mplayer = None
    self.deadPlayers = []
    
    while 1:
        anki.sound.mplayerEvt.wait()
        anki.sound.mplayerEvt.clear()
        
        # clearing queue?
        if anki.sound.mplayerClear and self.mplayer:
            try:
                self.mplayer.stdin.write("stop\n")
            except:
                # mplayer quit by user (likely video)
                self.deadPlayers.append(self.mplayer)
                self.mplayer = None
        
        # loop through files to play
        while anki.sound.mplayerQueue:
            # ensure started
            if not self.mplayer:
                my_startProcessHandler(self)
                #self.startProcess()
                
            # pop a file
            try:
                item = anki.sound.mplayerQueue.pop(0)      
            except IndexError:
                # queue was cleared by main thread
                continue
            if anki.sound.mplayerClear:
                anki.sound.mplayerClear = False
                extra = ""
            else:
                extra = " 1"
            cmd = 'loadfile "%s"%s\n' % (item, extra)
            
            try:
                self.mplayer.stdin.write(cmd)
            except:
                # mplayer has quit and needs restarting
                self.deadPlayers.append(self.mplayer)
                self.mplayer = None
                my_startProcessHandler(self)
                #self.startProcess()
                self.mplayer.stdin.write(cmd)

            if abs(audio_speed - 1.0) > 0.01:
                self.mplayer.stdin.write("af_add scaletempo=stride=10:overlap=0.8\n")
                self.mplayer.stdin.write("speed_set %f \n" % audio_speed)
                self.mplayer.stdin.write("seek 0 1\n")
                
            # Clear out rest of queue
            extraOutput = True
            while extraOutput:
                try:
                    extraLine = stdoutQueue.get_nowait()
                    #messageBuff += "ExtraLine: " + line
                except Empty:
                    extraOutput = False
            
            # Wait until the file finished playing before adding the next file
            finishedPlaying = False
            while not finishedPlaying and not anki.sound.mplayerClear:
                # poll stdout for an 'EOF code' message
                try:
                    line = stdoutQueue.get_nowait()
                    #messageBuff += line
                except Empty:
                    # nothing, sleep for a bit
                    finishedPlaying = False
                    time.sleep(0.05)
                else:
                    # check the line
                    #messageBuff += line
                    lineParts = line.split(':')
                    if lineParts[0] == 'EOF code':
                        finishedPlaying = True
            
            # Clear out rest of queue
            extraOutput = True
            while extraOutput:
                try:
                    extraLine = stdoutQueue.get_nowait()
                    #messageBuff += "ExtraLine: " + line
                except Empty:
                    extraOutput = False
            
        # if we feed mplayer too fast it loses files
        time.sleep(0.1)
        # end adding to queue
                
        # wait() on finished processes. we don't want to block on the
        # wait, so we keep trying each time we're reactivated
        def clean(pl):
            if pl.poll() is not None:
                pl.wait()
                return False
            else:
                showInfo("Clean")
                return True
        self.deadPlayers = [pl for pl in self.deadPlayers if clean(pl)]

def my_startProcessHandler(self):
    try:
        cmd = anki.sound.mplayerCmd + ["-slave", "-idle", '-msglevel', 'all=0:global=6']
        devnull = file(os.devnull, "w")
        
        # open up stdout PIPE to check when files are done playing
        self.mplayer = subprocess.Popen(
            cmd, startupinfo=anki.sound.si, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=devnull)

        # setup 
        t = Thread(target=enqueue_output, args=(self.mplayer.stdout, stdoutQueue))
        t.daemon = True
        t.start()
    except OSError:
        anki.sound.mplayerEvt.clear()
        raise Exception("Did you install mplayer?")

def store_file(regex_string):
    global audio_file
    audio_file = regex_string.group(1)
    
def audio_filter(qa_html, qa_type, dummy_fields, dummy_model, dummy_data, dummy_col):
    re.sub(sound_regex, store_file, qa_html)
    return qa_html

Reviewer._keyHandler = wrap(Reviewer._keyHandler, my_keyHandler)
MplayerMonitor.run = my_runHandler
MplayerMonitor.startProcess = my_startProcessHandler

addHook("mungeQA", audio_filter)